"""Fixture strategy: equal weights but a NaN final row (warmup-backstop trigger)."""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = inputs.data.array("Close").to_numpy()
    n_bars, n_symbols = close.shape
    weights = np.full((n_bars, n_candidates * n_symbols), 1.0 / n_symbols, dtype=float)
    weights[-1, :] = np.nan
    return weights
