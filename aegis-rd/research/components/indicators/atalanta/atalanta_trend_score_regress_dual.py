# %% component overview
# Atalanta DUAL regression-slope trend score - the same annualized OLS slope of log price as
# atalanta.trend_score_regress, computed at TWO lookbacks and emitted as two outputs: the SLOW
# `trend_score` (the consumed champion signal, byte-identical to atalanta.trend_score_regress at the
# same lookback) and a FAST `trend_score_fast`. The fast leg is NOT a trading signal - it exists only
# so a strategy can read it as a turning-point GATE (de-risk the slow position when the fast slope has
# already turned but the sticky slow latch has not). Pairing a slow trade signal with a fast
# turning-point read is the operational form of Harvey-Goulding-Mazzoleni "Breaking Bad Trends" (FAJ
# 2023): turning-point frequency drives weak trend, and reacting at the turn (fast/slow disagreement)
# improves risk-adjusted returns, where adding a fast trading leg only buys whipsaw
# ([[trend-following-in-whipsaw-regimes]]). Both lookbacks computed full-series so the warmup is
# incurred once, not per split window (the windowed-compute-in-indicator rule).

# %% imports
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_regress_dual",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["lookback", "fast_lookback"],
    "output_names": ["trend_score", "trend_score_fast"],
    "defaults": {"lookback": 189, "fast_lookback": 63},
}


# %% parameter space
def param_space():
    """Slow lookback pinned to the champion (189); fast lookback is the turning-point read.

    The slow leg is the live champion signal, so it is a single value here - this indicator only
    *adds* the fast gate read; it does not re-open the slow lookback search. The fast band spans the
    short ~2-3 month horizon at which a turn becomes visible well before the slow latch flips.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "lookback": vbt.Param([189]),
        "fast_lookback": vbt.Param([42, 63]),
    }


# %% lookback
def lookback(**params):
    """Warmup is the slower (longer) of the two slope windows."""
    return int(max(params["lookback"], params["fast_lookback"]))


# %% helpers
def _regress_slope_annualized(log_close, window):
    """Annualized OLS slope of log price over a fixed window: exp(slope_per_bar * 252) - 1.

    Identical to atalanta.trend_score_regress so the slow output matches the champion bit-for-bit:
    a fixed linear filter ``slope_t = w . log_close[t-window+1 : t+1]`` with weights
    ``w_k = (k - mean(k)) / Sxx`` - one vectorized sliding dot product, no per-window fit.
    """

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if window <= T and window >= 2:
        x = np.arange(window, dtype=np.float64)
        x_centered = x - x.mean()
        weights = x_centered / (x_centered @ x_centered)
        windows = sliding_window_view(log_close, window, axis=0)  # (T-window+1, n_symbols, window)
        slope = windows @ weights  # (T-window+1, n_symbols)
        out[window - 1 :] = np.exp(slope * 252.0) - 1.0

    out[:window] = np.nan
    return out


def _scores_for(log_close, lookbacks, n_candidates, n_symbols, T):
    """One annualized-slope panel per candidate, de-duplicated by lookback."""

    out = np.full((T, n_candidates * n_symbols), np.nan)
    cache: dict[int, np.ndarray] = {}
    for ci in range(n_candidates):
        lb = int(lookbacks[ci])
        if lb not in cache:
            cache[lb] = _regress_slope_annualized(log_close, lb)
        out[:, ci * n_symbols : (ci + 1) * n_symbols] = cache[lb]
    return out


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized slow + fast regression-slope trend scores for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    log_close = np.log(close.to_numpy().astype(np.float64))

    slow = _scores_for(log_close, param_lists["lookback"], n_candidates, n_symbols, T)
    fast = _scores_for(log_close, param_lists["fast_lookback"], n_candidates, n_symbols, T)

    return {"trend_score": slow, "trend_score_fast": fast}
