"""Fixture strategy: equal long weight 1/n on every bar (gross = net = 1.0)."""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = inputs.data.array("Close").to_numpy()
    n_bars, n_symbols = close.shape
    return np.full((n_bars, n_candidates * n_symbols), 1.0 / n_symbols, dtype=float)
