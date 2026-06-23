"""Fixture strategy: long weight proportional to trailing price CHANGE.

A *difference* feature — each symbol's weight tracks ``Close - Close[0]`` over the
window. A uniform additive price shift (a continuous-future re-base) cancels in the
difference, so the weights are unchanged: this strategy is additive-invariant. A row
with no positive change falls back to equal weight (also invariant). Long-only,
gross = net = 1.0.
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = np.asarray(inputs.data.array("Close").to_numpy(), dtype=float)
    change = close - close[0]  # difference from the window's first bar, per symbol
    positive = np.clip(change, 0.0, None)
    total = positive.sum(axis=1, keepdims=True)
    n_symbols = close.shape[1]
    weights = np.where(total > 0, positive / np.where(total > 0, total, 1.0), 1.0 / n_symbols)
    return np.tile(weights, (1, n_candidates))
