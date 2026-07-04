# %% component overview
# Atalanta trend score, REGRESSION-SLOPE variant - annualized least-squares slope of log price
# per symbol. A smoother, drop-in replacement for atalanta.trend_score (same output name and
# units: an annualized return whose sign is the trend direction and magnitude the strength), so
# any strategy that consumes "trend_score" takes it unchanged. The endpoint-to-endpoint score
# (C_t / C_{t-lb}) reads only two prices and flips sign on noise near zero; the OLS slope uses
# every bar in the window, so the sign is steadier and the book changes state less often - fewer
# whipsaw round-trips, which is the dominant cost under a fixed per-order fee. A smoother trend
# rule cuts turnover materially with no significant risk-adjusted-return loss (Baltas & Kosowski).
# Still ABSOLUTE/time-series momentum (price vs its own past) and still de-risks in downtrends
# (slope < 0 -> negative score -> the strategy's sign gate goes flat), so the lookback-straddle
# convexity is preserved. Lookbacks span the slow convex band (~6-12mo) where trend convexity
# lives at the quarterly measurement horizon ([[what-makes-a-trend-sleeve-convex]]).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_regress",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback"],
    "output_names": ["trend_score"],
    "defaults": {"lookback": 189},
}


# %% parameter space
def param_space():
    """VBT-native lookbacks over the SLOW trend band only.

    The fast end is dropped on purpose: it trades more and puts its convexity at sub-monthly
    horizons that are neither measured nor wanted here, and long trends have not decayed the way
    short trends have. The slow band is where the smoothed slope's steadiness pays.
    """

    return {
        "lookback": vbt.Param([126, 189, 252]),
    }


# %% lookback
def lookback(**params):
    """Warmup bars for the regression score: the slope window length."""
    return int(params["lookback"])


# %% helpers
def _regress_slope_annualized(log_close, window):
    """Annualized OLS slope of log price over a fixed window: exp(slope_per_bar * 252) - 1.

    The regressor (0..window-1) is identical for every window, so the slope is a fixed
    linear filter ``slope_t = w . log_close[t-window+1 : t+1]`` with weights
    ``w_k = (k - mean(k)) / Sxx`` - one vectorized sliding dot product, no per-window fit.
    Computed on the full series so the window warmup is incurred once, not per split window
    (the windowed-compute-in-indicator rule).
    """

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if T >= window and window >= 2:
        x = np.arange(window, dtype=np.float64)
        x_centered = x - x.mean()
        weights = x_centered / (x_centered @ x_centered)
        windows = sliding_window_view(log_close, window, axis=0)  # (T-window+1, n_symbols, window)
        slope = windows @ weights  # (T-window+1, n_symbols)
        out[window - 1 :] = np.exp(slope * 252.0) - 1.0

    # Rows before a full window are incomplete -> NaN so the strategy's sign gate
    # excludes warmup bars rather than reading a partial trend (matches atalanta.trend_score).
    out[:window] = np.nan
    return out


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized Atalanta regression-slope trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    lookbacks = param_lists["lookback"]

    log_close = np.log(close.to_numpy().astype(np.float64))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for lb in set(lookbacks):
        candidate_indices = [i for i in range(n_candidates) if lookbacks[i] == lb]
        arr = _regress_slope_annualized(log_close, int(lb))
        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"trend_score": result}
