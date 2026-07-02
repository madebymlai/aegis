"""Fixture strategy: 100% weight on one native InstrumentId column."""

import numpy as np


def run(inputs, *, n_candidates, **params):
    close = inputs.data.array("Close")
    target = [column.value for column in close.columns].index("AAPL.NASDAQ")
    n_bars, n_symbols = close.shape
    weights = np.zeros((n_bars, n_candidates * n_symbols), dtype=float)
    weights[:, target] = 1.0
    return weights
