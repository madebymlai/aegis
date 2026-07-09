"""Fixture strategy: long weight proportional to trailing percentage return.

A *multiplicatively stable* feature — each symbol's weight tracks
``Close / Close[0] - 1``, so a uniform per-column scale (a ratio re-base)
cancels and the weights are unchanged. A uniform additive shift does NOT
cancel (``(p + s) / (p0 + s)`` is a different ratio), so this strategy is
spread-sensitive. Rows with no positive return fall back to equal weight.
Long-only, gross = net = 1.0.
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = np.asarray(inputs.data.array("Close").to_numpy(), dtype=float)
    returns = close / close[0] - 1.0  # trailing pct return per symbol
    positive = np.clip(returns, 0.0, None)
    total = positive.sum(axis=1, keepdims=True)
    n_symbols = close.shape[1]
    weights = np.where(total > 0, positive / np.where(total > 0, total, 1.0), 1.0 / n_symbols)
    return np.tile(weights, (1, n_candidates))
