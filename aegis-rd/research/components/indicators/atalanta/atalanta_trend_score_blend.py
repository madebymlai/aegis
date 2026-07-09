# %% component overview
# Atalanta trend score, BARBELL-BLEND variant - a single blended annualized OLS slope that mixes a
# SLOW horizon (the champion's lb189) with a FAST horizon (~1-2mo) at the SIGNAL level, so the
# downstream keystone consumes ONE "trend_score" and stays byte-unchanged. This is the CORRECT
# barbell construction: combine the two slopes into one score and run one book, NOT an average of
# two weight books (that averaged-sub-portfolio form is the rebalancing-premium CONCAVE trap that
# killed the archived long-only barbell - ThinkNewfound "Ensembles and Rebalancing"). The literature
# (Man AHL "Need for Speed"; Goulding-Harvey-Mazzoleni "Momentum Turning Points" JFE 2023; arXiv
# 2510.23150 barbell) places crisis convexity and turning-point tail-truncation at the SHORT end,
# which a single slow lookback cannot express. See [[notes/trend-speed-buys-drawdown-not-convexity]].
#
# SCALE PRESERVATION (why this is a clean nested test): the champion's enter/exit bands (0.10/0.05)
# and one-sided short_cap (0.10) are calibrated in the SLOW slope's annualized-return units. A raw
# fast slope is far larger in magnitude and would silently re-scale those thresholds - the exact
# confound that makes a "barbell" result unreadable. So the fast slope is rescaled to the slow
# slope's trailing volatility (causal rolling std over `scale_window`) BEFORE blending. The blend
# then keeps the slow slope's scale, and every champion threshold stays meaningful. At blend_w = 0
# the output is the slow slope bit-for-bit, so blend_w=0 reproduces the locked champion (conv 0.447).

# %% imports
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_blend",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["slow_lookback", "fast_lookback", "blend_w", "scale_window"],
    "output_names": ["trend_score"],
    "defaults": {"slow_lookback": 189, "fast_lookback": 30, "blend_w": 0.0, "scale_window": 252},
}


# %% parameter space
def param_space():
    """Sweep the barbell weight; horizons and the scale window are pinned by the config.

    ``blend_w`` 0.0 is the nested champion control (pure slow slope). The interior cells trace the
    convexity/drawdown-vs-slow frontier; 0.50 is an equal barbell. Only ``blend_w`` is multi-valued
    so mu-noise stays off the ranker.
    """

    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {
        "slow_lookback": vbt.Param([189]),
        "fast_lookback": vbt.Param([30]),
        "blend_w": vbt.Param([0.0, 0.15, 0.30, 0.50]),
        "scale_window": vbt.Param([252]),
    }


# %% lookback
def lookback(**params):
    """Warmup: the longest window in play (slow slope or the fast-scale std window)."""
    return int(max(params["slow_lookback"], params["scale_window"]))


# %% helpers
def _regress_slope_annualized(log_close, window):
    """Annualized OLS slope of log price over a fixed window (identical to trend_score_regress).

    Fixed linear filter ``slope_t = w . log_close[t-window+1 : t+1]`` with weights
    ``w_k = (k - mean(k)) / Sxx``; one vectorized sliding dot product, computed on the full series.
    """

    T, n_symbols = log_close.shape
    out = np.full((T, n_symbols), np.nan)
    if T >= window and window >= 2:
        x = np.arange(window, dtype=np.float64)
        x_centered = x - x.mean()
        weights = x_centered / (x_centered @ x_centered)
        windows = sliding_window_view(log_close, window, axis=0)  # (T-window+1, n_symbols, window)
        slope = windows @ weights
        out[window - 1 :] = np.exp(slope * 252.0) - 1.0
    out[:window] = np.nan
    return out


def _trailing_std(arr, window):
    """Causal trailing std per column (uses only rows up to and including t); NaN until a full window."""

    return pd.DataFrame(arr).rolling(window, min_periods=window).std().to_numpy()


def _blended_score(log_close, slow_lb, fast_lb, blend_w, scale_window):
    """Blend the slow and fast annualized slopes, fast rescaled to the slow slope's trailing vol.

    ``blend_w = 0`` returns the slow slope unchanged (the champion). Otherwise the fast slope is
    scaled per-column by ``std_slow / std_fast`` (causal, over ``scale_window``) so the blend keeps
    the slow slope's units, then blended as ``(1 - w) * slow + w * fast_scaled``.
    """

    slow = _regress_slope_annualized(log_close, slow_lb)
    if blend_w == 0.0:
        return slow

    fast = _regress_slope_annualized(log_close, fast_lb)
    std_slow = _trailing_std(slow, scale_window)
    std_fast = _trailing_std(fast, scale_window)
    ratio = np.where((std_fast > 1e-9) & np.isfinite(std_slow), std_slow / std_fast, 1.0)
    fast_scaled = fast * ratio
    return (1.0 - blend_w) * slow + blend_w * fast_scaled


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized barbell-blend trend score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)

    log_close = np.log(close.to_numpy().astype(np.float64))
    slow_lbs = param_lists["slow_lookback"]
    fast_lbs = param_lists["fast_lookback"]
    blend_ws = param_lists["blend_w"]
    scale_windows = param_lists["scale_window"]

    result = np.full((T, n_candidates * n_symbols), np.nan)
    cache = {}
    for ci in range(n_candidates):
        key = (int(slow_lbs[ci]), int(fast_lbs[ci]), float(blend_ws[ci]), int(scale_windows[ci]))
        if key not in cache:
            cache[key] = _blended_score(log_close, key[0], key[1], key[2], key[3])
        result[:, ci * n_symbols : (ci + 1) * n_symbols] = cache[key]

    return {"trend_score": result}
