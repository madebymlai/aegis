# %% component overview
# Atalanta trend score, SIGNIFICANCE-WEIGHTED regression variant - the champion's annualized OLS
# slope of log price scaled by the fit's own R^2 raised to a `significance` exponent:
#     trend_score = (exp(slope * 252) - 1) * R^2 ** significance
# A drop-in for atalanta.trend_score_regress (same output name and units - an annualized return whose
# sign is the trend direction and magnitude the strength), so keystone_shortmute consumes it
# unchanged. The raw slope reports only the DIRECTION and STEEPNESS of the best-fit line; it says
# nothing about how well that line actually FITS. Two windows with the same slope - one a clean ramp,
# one a saw-tooth that happens to end higher - score identically, yet only the first is a trend worth
# riding. R^2 is exactly that missing coordinate: the fraction of the window's log-price variance the
# linear trend explains (~1 for a clean directional move, ~0 for sideways chop). Weighting the score
# by R^2 ** significance down-weights the slope precisely when the fit is poor - it stands aside in the
# trendless whipsaw regimes where the sleeve bleeds, while leaving the clean crisis trends (high R^2)
# it is hired to ride essentially untouched.
#
# LINEAGE. This is the continuous, unit-preserving form of two state-of-the-art "significance-aware"
# trend signals: Baltas & Kosowski's TREND (the t-statistic t(beta)=beta/SE(beta) of the slope, which
# for a fixed window is a monotone transform of R^2 since t^2 = R^2 (n-2)/(1-R^2)) and Bryhn &
# Dimberg's "statistically meaningful trend" (trade only when R^2 >= 0.65 and p <= 0.05). Both cut
# turnover to a fraction of the naive signal at equal pre-cost Sharpe by not trading noise. We keep
# the CHAMPION'S annualized-return units (so the enter/exit dead-zone bands 0.10/0.05 and the
# magnitude response still apply) and use a SOFT R^2 weight rather than the SMT hard gate (a 0.65
# cliff plus full abstention is brittle and risks turn-gate lag on this thin 3-leg book).
#
# NESTING. At significance = 0.0, R^2 ** 0 = 1 for every window, so trend_score reduces to the
# champion's regression slope byte-for-byte (the code branches to skip the R^2 weight entirely at
# gamma = 0, so the nested control is exact, not merely close). significance > 0 progressively shrinks
# the slope in low-R^2 regimes only. Still ABSOLUTE/time-series momentum, still de-risks in
# downtrends, so the lookback-straddle convexity is preserved ([[what-makes-a-trend-sleeve-convex]]).
# Computed on the full series so the window warmup is incurred once (the windowed-compute-in-indicator
# rule); a strictly CAUSAL trailing window (live-research parity).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_meaningful",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback", "significance"],
    "output_names": ["trend_score"],
    "defaults": {"lookback": 189, "significance": 0.0},
}


# %% parameter space
def param_space():
    """Sweep the significance exponent at the CHAMPION lookback (189, pinned).

    The lookback is fixed to the champion's slow-band value so the grid isolates one lever - how hard
    to down-weight statistically-weak trends. ``significance`` spans champion (0.0, no weighting) ->
    gentle (0.5) -> moderate (1.0) -> aggressive (2.0), where R^2 ** 2 pushes a chop window (R^2 ~ 0.2)
    to ~0.04x while leaving a clean trend (R^2 ~ 0.9) at ~0.81x.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "lookback": vbt.Param([189]),
        "significance": vbt.Param([0.0, 0.5, 1.0, 2.0]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for the regression score: the slope/R^2 window length."""
    return int(params["lookback"])


# %% helpers
def _meaningful_score(log_close, window, significance):
    """Annualized OLS slope of log price weighted by R^2 ** significance, per symbol.

    The slope arm is identical to atalanta.trend_score_regress: a fixed linear filter
    ``slope_t = w . log_close[t-window+1 : t+1]`` with weights ``w_k = (k - mean(k)) / Sxx``, one
    vectorized sliding dot product. R^2 for the same window is ``slope^2 * Sxx / Syy`` (the identity
    R^2 = Sxy^2 / (Sxx Syy) with Sxy = slope * Sxx), clamped to [0, 1]. At significance == 0 the R^2
    factor is skipped so the result equals the champion slope byte-for-byte.
    """

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if T >= window and window >= 2:
        x = np.arange(window, dtype=np.float64)
        x_centered = x - x.mean()
        sxx = x_centered @ x_centered
        weights = x_centered / sxx
        windows = sliding_window_view(log_close, window, axis=0)  # (M, n_symbols, window)
        slope = windows @ weights  # (M, n_symbols) = Sxy / Sxx
        score = np.exp(slope * 252.0) - 1.0
        if significance == 0.0:
            out[window - 1 :] = score  # nested champion: no R^2 weighting, byte-exact
        else:
            y_mean = windows.mean(axis=2)  # (M, n_symbols)
            syy = ((windows - y_mean[:, :, None]) ** 2).sum(axis=2)  # total sum of squares
            r2 = np.zeros_like(slope)
            nz = syy > 0.0  # flat window -> slope 0 -> score 0; leave R^2 = 0 harmlessly
            r2[nz] = (slope[nz] ** 2) * sxx / syy[nz]
            np.clip(r2, 0.0, 1.0, out=r2)
            out[window - 1 :] = score * (r2**significance)

    # Rows before a full window are incomplete -> NaN so the strategy's sign gate excludes warmup
    # bars rather than reading a partial trend (matches atalanta.trend_score_regress exactly).
    out[:window] = np.nan
    return out


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta significance-weighted trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    lookbacks = param_lists["lookback"]
    significances = param_lists["significance"]

    log_close = np.log(close.to_numpy().astype(np.float64))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for lb, sig in {(int(lookbacks[i]), float(significances[i])) for i in range(n_candidates)}:
        candidate_indices = [
            i
            for i in range(n_candidates)
            if int(lookbacks[i]) == lb and float(significances[i]) == sig
        ]
        arr = _meaningful_score(log_close, int(lb), float(sig))
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"trend_score": result}
