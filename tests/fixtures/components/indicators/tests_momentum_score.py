# %% component overview
# Vanguard multi-period momentum score indicator.
# Composite trend strength across four annualized return horizons.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "tests.momentum_score",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"],
    "output_names": ["momentum_score"],
    "defaults": {
        "h1": 21,
        "h2": 63,
        "h3": 126,
        "h4": 252,
        "w1": 12.0,
        "w2": 4.0,
        "w3": 2.0,
        "w4": 1.0,
    },
}


# %% parameter space
def param_space():
    """Return VBT-native multi-period momentum params for optimization."""

    return {
        "h1": vbt.Param([15, 21, 30]),
        "h2": vbt.Param([42, 63, 84]),
        "h3": vbt.Param([100, 126, 180]),
        "h4": vbt.Param([200, 252, 300]),
        "w1": vbt.Param([8.0, 12.0, 16.0]),
        "w2": vbt.Param([2.0, 4.0, 6.0]),
        "w3": vbt.Param([1.0, 2.0, 3.0]),
        "w4": vbt.Param([0.5, 1.0, 2.0]),
    }


# %% helpers
def _compute_score(close, h1, h2, h3, h4, w1, w2, w3, w4):
    """Compute multi-period annualized momentum score for one parameter tuple."""

    horizons = (h1, h2, h3, h4)
    weights = (w1, w2, w3, w4)
    max_horizon = max(horizons)

    score = np.zeros_like(close.values, dtype=np.float64)
    for h, w in zip(horizons, weights, strict=True):
        annualized = (close / close.shift(h)) ** (252 / h) - 1.0
        score += w * annualized.values

    # Rows before max horizon are incomplete — NaN so downstream gates
    # (absolute momentum: score > 0) correctly exclude warmup bars.
    score[:max_horizon] = np.nan

    return close.__class__(score, index=close.index, columns=close.columns)


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized multi-period momentum score for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)

    h1s = param_lists["h1"]
    h2s = param_lists["h2"]
    h3s = param_lists["h3"]
    h4s = param_lists["h4"]
    w1s = param_lists["w1"]
    w2s = param_lists["w2"]
    w3s = param_lists["w3"]
    w4s = param_lists["w4"]

    result = np.full((T, n_candidates * n_symbols), np.nan)

    unique_combos = set(zip(h1s, h2s, h3s, h4s, w1s, w2s, w3s, w4s, strict=True))
    for h1, h2, h3, h4, w1, w2, w3, w4 in unique_combos:
        candidate_indices = [
            i
            for i in range(n_candidates)
            if h1s[i] == h1
            and h2s[i] == h2
            and h3s[i] == h3
            and h4s[i] == h4
            and w1s[i] == w1
            and w2s[i] == w2
            and w3s[i] == w3
            and w4s[i] == w4
        ]

        score_df = _compute_score(
            close,
            int(h1),
            int(h2),
            int(h3),
            int(h4),
            float(w1),
            float(w2),
            float(w3),
            float(w4),
        )
        arr = score_df.values

        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"momentum_score": result}
