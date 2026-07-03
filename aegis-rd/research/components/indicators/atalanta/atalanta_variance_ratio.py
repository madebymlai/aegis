# %% component overview
# Atalanta variance ratio - rolling Lo-MacKinlay (1988) overlapping variance ratio VR(k) per symbol,
# a memory/persistence gauge for the trend legs. Under a random walk the variance of k-period returns
# is exactly k times the one-period variance, so VR(k) = Var_k / (k * Var_1) = 1. VR(k) > 1 signals
# POSITIVE autocorrelation (a move at horizon k tends to persist - momentum-friendly); VR(k) < 1
# signals MEAN REVERSION (the move tends to reverse - whipsaw-prone). It is a pure measurement: the
# strategy decides how to act on it (Tell-Don't-Ask), the way trend_score and realized_vol are pure
# readings the keystone consumes.
#
# WHY (h54, [[is-the-trend-premium-decaying]]): Mehlitz & Auer (2024), "Memory-enhanced momentum in
# commodity futures markets" (Eur. J. Finance 30(8):773-802), resurrect a decayed commodity-momentum
# signal by CONDITIONING it on autocorrelation - trusting the trend where a variance ratio says the
# series has memory (VR > 1) and standing aside where it says the series mean-reverts (VR < 1). Their
# VR-conditioned momentum beats naive TSMOM on reward/risk, avoids momentum crashes, and survives
# costs, out-of-sample and data-snooping. Their design is CROSS-SECTIONAL selection across many
# commodities; this book holds only two commodity names (IGLN gold, ICOM broad), so the adaptation is
# a per-leg TIME-SERIES gate - the memgate strategy mutes a commodity leg's trend toward cash while
# its own VR sits in the mean-reverting zone, leaving the borrow-gated IDTL leg untouched.
#
# Computed on the full series so the rolling warmup is incurred once, not re-incurred per split window
# (the windowed-compute-in-indicator rule), and via one sliding-window dot like trend_score_regress.
#
# NEUTRAL-LEVEL CALIBRATION (validated numerically, test_vr.py): the estimator is bit-for-bit the
# textbook Lo-MacKinlay overlapping VR and matches the analytic AR(1) VR to <0.02, but the ROLLING
# random-walk neutral is not exactly 1.0 - over a finite window the m-correction leaves a small
# residual: measured neutral is ~1.00 at the pinned default (k=21, W=252), ~0.99 for short windows
# (W=126), and drifts to ~1.02 for long horizons/windows (k=42 or W>=504). So a consuming gate should
# threshold on the estimator's MEASURED neutral for its (k, W), not a naive 1.0, and - because the
# rolling ratio is autocorrelated and noisy bar-to-bar - apply a dead-band / hysteresis around it
# (that robustness is the strategy's job, keeping this component a pure measurement).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.variance_ratio",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["vr_horizon", "vr_window"],
    "output_names": ["variance_ratio"],
    "defaults": {"vr_horizon": 21, "vr_window": 252},
}


# %% parameter space
def param_space():
    """VBT-native (horizon, window) grid for the memory gate.

    ``vr_horizon`` (k) is the memory horizon whose persistence is tested: the whipsaw reversals that
    hurt the slow sleeve are the days-to-weeks V-reversals, so k spans weekly-to-monthly-to-two-month.
    ``vr_window`` (W) is the rolling estimation sample - it must be well above k for a stable ratio and
    is sized around the trend lookback (lb189) so the gauge characterises the same regime the trend
    trades: 126 (~6mo, responsive) to 252 (~1yr, steadier). The product stays small; in the live test
    the pair is PINNED (like lb189 / vw126) and the strategy's gate threshold is the swept lever.
    """

    return {
        "vr_horizon": vbt.Param([10, 21, 42]),
        "vr_window": vbt.Param([126, 252]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars: the estimation window needs `vr_window` one-period returns before a first ratio."""
    return int(params["vr_window"])


# %% helpers
def _rolling_variance_ratio(log_close, k, window):
    """Rolling Lo-MacKinlay overlapping VR(k) over a trailing `window` of one-period log returns.

    Per window of ``window`` one-period returns (``window + 1`` log prices), with mean drift
    ``mu = mean(one-period returns)``:
      - one-period variance (unbiased):  sigma2_1 = sum((r - mu)^2) / (window - 1)
      - k-period variance (overlapping, unbiased):  sigma2_k = sum((y - k*mu)^2) / m,
        where the overlapping k-period returns are ``y_s = logP_s - logP_{s-k}`` and the Lo-MacKinlay
        bias correction is ``m = k * (window - k + 1) * (1 - k/window)``.
      - VR = sigma2_k / sigma2_1.
    Vectorized across all windows and symbols with one ``sliding_window_view`` (no per-window loop),
    the ratio landing on the window's last bar so it is causal (uses only trailing data).
    """

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    prices_per_window = window + 1  # `window` one-period returns need window+1 prices
    if T >= prices_per_window and k >= 2 and window > k:
        wins = sliding_window_view(log_close, prices_per_window, axis=0)  # (Nw, n_symbols, window+1)
        r = np.diff(wins, axis=-1)  # one-period log returns: (Nw, n_symbols, window)
        mu = r.mean(axis=-1, keepdims=True)  # per-window drift: (Nw, n_symbols, 1)
        var1 = np.square(r - mu).sum(axis=-1) / (window - 1)  # (Nw, n_symbols)

        y = wins[..., k:] - wins[..., :-k]  # overlapping k-period returns: (Nw, n_symbols, window-k+1)
        m = k * (window - k + 1) * (1.0 - k / window)
        vark = np.square(y - k * mu).sum(axis=-1) / m  # (Nw, n_symbols)

        with np.errstate(divide="ignore", invalid="ignore"):
            vr = np.where(var1 > 0.0, vark / var1, np.nan)  # flat window -> undefined -> NaN
        out[prices_per_window - 1 :] = vr

    # Rows before a full window are incomplete -> NaN so the gate reads "no info" on warmup rather
    # than a partial ratio (matches trend_score_regress / realized_vol warmup semantics).
    out[:window] = np.nan
    return out


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta rolling variance ratio for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    horizons = param_lists["vr_horizon"]
    windows = param_lists["vr_window"]

    log_close = np.log(close.to_numpy().astype(np.float64))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for pair in {(int(horizons[i]), int(windows[i])) for i in range(n_candidates)}:
        k, w = pair
        candidate_indices = [
            i for i in range(n_candidates) if (int(horizons[i]), int(windows[i])) == pair
        ]
        arr = _rolling_variance_ratio(log_close, k, w)
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"variance_ratio": result}
