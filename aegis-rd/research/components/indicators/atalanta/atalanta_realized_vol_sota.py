# %% component overview
# Atalanta realized volatility, SOTA-ESTIMATOR variant - a drop-in replacement for atalanta.realized_vol
# (same output name "realized_vol" and units: annualized vol per symbol) that swaps the CLOSE-TO-CLOSE
# rolling std for a more efficient estimator, selected by the ``estimator`` param. The champion's estimator
# is the 1x-efficiency baseline; the trend-following literature is explicit that a better estimator is a
# TURNOVER lever, not a return lever - Baltas & Kosowski (CME) show the volatility estimator has no
# economically significant effect on pre-cost Sharpe, but Yang-Zhang cuts portfolio turnover ~17% (up to
# ~36% with a smooth trend rule) "without a statistically significant performance impact". On a fixed-per-
# order-fee EUR 5k book, that turnover cut IS net return. So this variant is tested for: same convexity,
# fewer fills / lower fees.
#
# ESTIMATORS (all annualized x sqrt(252); same warmup = vol_window bars, so the strategy's sizing sees
# identical NaN warmup regardless of choice):
#  - "ctc"  CLOSE-TO-CLOSE: rolling std of daily log returns, ddof=1 - byte-identical to atalanta.realized_vol
#           (the champion; the nested parity control).
#  - "ewma" EXPONENTIALLY-WEIGHTED close-to-close: ewm(span=vol_window).std(). span=W is chosen so the EWMA
#           mean age (W-1)/2 MATCHES the equal-weighted window's mean age - it isolates exp-vs-equal weighting
#           at equal memory (MOP/RiskMetrics family, the Claremont-thesis "slow EWMA of a 6-month window cuts
#           turnover and smooths weights"). Deliberately NOT the canonical fast lambda=0.94 (~17-day memory):
#           RA show a long trend lookback tied to a SHORT vol window "all but negates positive skew", so a
#           fast EWMA is convexity-hostile on this long-lb189 book - the matched-memory slow EWMA is the
#           correct convex-book choice.
#  - "yang_zhang" YANG-ZHANG (2000) range estimator over OHLC: overnight var + k*open-close var + (1-k)*
#           Rogers-Satchell, k = 0.34/(1.34+(W+1)/(W-1)). The SOTA daily-OHLC estimator (8-14x efficient,
#           drift-independent, min-variance unbiased; Baltas-Kosowski's chosen estimator). Range estimators
#           are more sensitive to bad H/L prints, so ctc stays the robust baseline (FlashAlpha caveat).
#
# Computed on the full series so the rolling warmup is incurred once, not per split window.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.realized_vol_sota",
    "version": "1.0.0",
    "input_names": ["Open", "High", "Low", "Close"],
    "param_names": ["vol_window", "estimator"],
    "output_names": ["realized_vol"],
    "defaults": {"vol_window": 126, "estimator": "ctc"},
}

_ANNUAL = np.sqrt(252.0)


# %% parameter space
def param_space():
    """The champion window pinned; the estimator is the swept lever (loop-edited in the config, since a
    config rejects a list indicator param). ``ctc`` reproduces the champion exactly - the parity control."""

    return {
        "vol_window": vbt.Param([126]),
        "estimator": vbt.Param(["ctc", "ewma", "yang_zhang"]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars: the estimation window length (identical across estimators)."""
    return int(params["vol_window"])


# %% helpers
def _ctc(close, window):
    """Close-to-close: annualized rolling std of daily log returns (ddof=1) - the champion, byte-for-byte."""

    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std(ddof=1) * _ANNUAL


def _ewma(close, window):
    """Exponentially-weighted close-to-close at span=window (mean age matched to the equal window).

    ``min_periods=window`` reproduces the ctc warmup (first window-1 bars NaN) so the estimator swap never
    changes which bars are sized.
    """

    log_ret = np.log(close / close.shift(1))
    return log_ret.ewm(span=window, min_periods=window).std() * _ANNUAL


def _yang_zhang(open_, high, low, close, window):
    """Yang-Zhang (2000) annualized vol over a rolling ``window`` of OHLC bars.

    sigma^2 = sigma_overnight^2 + k*sigma_open_close^2 + (1-k)*sigma_RS^2, with the overnight and
    open-close terms rolling variances (ddof=1), the Rogers-Satchell term a rolling mean of the per-bar
    RS estimator, and k = 0.34 / (1.34 + (W+1)/(W-1)).
    """

    n = int(window)
    prev_close = close.shift(1)
    lo = np.log(open_ / prev_close)  # overnight (close -> next open)
    lc = np.log(close / open_)  # open -> close
    lu = np.log(high / open_)  # open -> high
    ld = np.log(low / open_)  # open -> low

    k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))
    var_o = lo.rolling(n).var(ddof=1)
    var_c = lc.rolling(n).var(ddof=1)
    rs = lu * (lu - lc) + ld * (ld - lc)  # per-bar Rogers-Satchell (drift-independent)
    var_rs = rs.rolling(n).mean()

    var_yz = var_o + k * var_c + (1.0 - k) * var_rs
    return np.sqrt(var_yz.clip(lower=0.0)) * _ANNUAL


def _estimate(data, window, estimator):
    """Dispatch to the chosen estimator; returns an annualized-vol DataFrame (T x n_symbols)."""

    close = data.array("Close")
    if estimator == "ctc":
        return _ctc(close, window)
    if estimator == "ewma":
        return _ewma(close, window)
    if estimator == "yang_zhang":
        return _yang_zhang(data.array("Open"), data.array("High"), data.array("Low"), close, window)
    raise ValueError(f"unknown estimator {estimator!r} (expected ctc | ewma | yang_zhang)")


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta SOTA realized vol for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["vol_window"]
    estimators = param_lists["estimator"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    for pair in {(int(windows[i]), str(estimators[i])) for i in range(n_candidates)}:
        w, est = pair
        arr = _estimate(data, w, est).values
        for ci in range(n_candidates):
            if (int(windows[ci]), str(estimators[ci])) == pair:
                result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"realized_vol": result}
