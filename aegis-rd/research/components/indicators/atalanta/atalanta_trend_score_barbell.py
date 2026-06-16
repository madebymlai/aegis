# %% component overview
# Atalanta barbell trend score — annualized absolute momentum at a FAST and a SLOW lookback,
# emitted as two outputs so a barbell strategy can build per-horizon sub-books and average them
# (the sub-portfolio ensemble that preserves fast crisis flips). Both computed full-series so the
# lookback warmup is incurred once, not per split window (the windowed-compute-in-indicator rule).
# Barbell (short+long, skip medium) is the diversifying combination per arXiv 2510.23150 +
# Hurst-Ooi-Pedersen; see aegis-rd-167.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "atalanta.trend_score_barbell",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["fast_lookback", "slow_lookback"],
    "output_names": ["trend_score_fast", "trend_score_slow"],
    "defaults": {"fast_lookback": 63, "slow_lookback": 252},
}


# %% parameter space
def param_space():
    """Fast and slow absolute-momentum lookbacks for the barbell."""

    return {
        "fast_lookback": vbt.Param([63]),
        "slow_lookback": vbt.Param([252]),
    }


# %% lookback
def lookback(**params):
    """Warmup is the slower (longer) lookback."""
    return int(max(params["fast_lookback"], params["slow_lookback"]))


# %% helpers
def _trend_score(close, lb):
    """Annualized absolute momentum (Close/Close.shift(lb))^(252/lb) - 1, NaN before warmup."""

    annualized = (close / close.shift(lb)) ** (252.0 / lb) - 1.0
    score = annualized.values.astype(np.float64)
    score[:lb] = np.nan
    return score


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized fast + slow trend scores for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    fasts = param_lists["fast_lookback"]
    slows = param_lists["slow_lookback"]

    out_fast = np.full((T, n_candidates * n_symbols), np.nan)
    out_slow = np.full((T, n_candidates * n_symbols), np.nan)
    for ci in range(n_candidates):
        out_fast[:, ci * n_symbols : (ci + 1) * n_symbols] = _trend_score(close, int(fasts[ci]))
        out_slow[:, ci * n_symbols : (ci + 1) * n_symbols] = _trend_score(close, int(slows[ci]))

    return {"trend_score_fast": out_fast, "trend_score_slow": out_slow}
