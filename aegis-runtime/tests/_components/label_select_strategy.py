"""Fixture strategy: 100% weight on the column whose authored label is 'A'.

Looks the instrument up by label (not position), so it only works if the
runtime relabels FIGI-keyed input back into the components' authored label space.
"""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = inputs.data.array("Close")
    target = list(close.columns).index("A")
    n_bars, n_symbols = close.shape
    weights = np.zeros((n_bars, n_candidates * n_symbols), dtype=float)
    weights[:, target] = 1.0
    return weights
