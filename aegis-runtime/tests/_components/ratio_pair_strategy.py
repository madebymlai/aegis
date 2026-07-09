"""Fixture strategy: weights driven by the ES/NQ price RATIO (column 0 / column 1).

The cross-root cancellation case for ratio mode: a COMMON multiplicative
re-base of both roots cancels in the ratio, but roots roll independently —
scaling one root alone changes the ratio and therefore the weights. A
per-root probe must reject this; an all-roots-at-once probe would not.
Long-only, rows sum to 1.0.
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = np.asarray(inputs.data.array("Close").to_numpy(), dtype=float)
    ratio = close[:, [0]] / close[:, [1]]
    w0 = ratio / (1.0 + ratio)
    weights = np.concatenate([w0, 1.0 - w0], axis=1)
    return np.tile(weights, (1, n_candidates))
