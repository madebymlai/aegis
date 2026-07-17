"""Fixture strategy: weights driven by the ES-NQ price SPREAD (column 0 - column 1).

The cross-root cancellation case for spread mode: a COMMON additive re-base
of both roots cancels in the level difference, but roots roll independently —
shifting one root alone changes the spread and therefore the weights. A
per-root probe must reject this; an all-roots-at-once probe would not.
Long-only, rows sum to 1.0, weights bounded in (0, 1).
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = np.asarray(inputs.data.array("Close").to_numpy(), dtype=float)
    spread = close[:, [0]] - close[:, [1]]
    w0 = 0.5 * (1.0 + spread / (1.0 + np.abs(spread)))
    weights = np.concatenate([w0, 1.0 - w0], axis=1)
    return np.tile(weights, (1, n_candidates))
