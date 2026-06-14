"""Fixture indicator: echoes the (already base-converted) Close panel.

Lets a test assert the strategy sees prices after currency conversion, and
exercises the indicator wiring + output-name/shape validation in compute_weights.
"""

import numpy as np


def run(data, *, n_candidates, **params):
    close = np.asarray(data.array("Close").to_numpy(), dtype=float)
    n_bars, n_symbols = close.shape
    return {"echo": close.reshape(n_bars, n_candidates * n_symbols)}
