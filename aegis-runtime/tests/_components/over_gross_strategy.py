"""Fixture strategy: 0.75 long per symbol — gross 1.5 on a two-symbol book,
breaching the unit-gross sleeve contract."""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = inputs.data.array("Close").to_numpy()
    n_bars, n_symbols = close.shape
    return np.full((n_bars, n_candidates * n_symbols), 0.75, dtype=float)
