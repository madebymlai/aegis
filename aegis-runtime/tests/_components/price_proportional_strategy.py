"""Fixture strategy: long weight proportional to each symbol's Close.

Weights reflect the price panel the strategy is handed — which is post-FX-
conversion — so a test can prove currency conversion ran before the strategy.
Each row sums to 1.0 (gross = net = 1.0, long-only).
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = np.asarray(inputs.data.array("Close").to_numpy(), dtype=float)
    weights = close / close.sum(axis=1, keepdims=True)
    return np.tile(weights, (1, n_candidates))
