# %% component overview
# Vanguard realized volatility — annualized rolling vol for inverse-vol sizing.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "tests.realized_vol",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["window"],
    "output_names": ["realized_vol"],
    "defaults": {"window": 20},
}


# %% parameter space
def param_space():
    """Return VBT-native realized-vol params for optimization."""

    return {
        "window": vbt.Param(list(range(10, 41))),
    }


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Vectorized realized volatility for all candidates in a single call."""

    close = data.array("Close")
    n_symbols = len(close.columns)
    T = len(close)
    windows = param_lists["window"]

    log_returns = np.log(close / close.shift(1))
    result = np.full((T, n_candidates * n_symbols), np.nan)

    for w in set(windows):
        candidate_indices = [i for i in range(n_candidates) if windows[i] == w]
        w = int(w)
        vol = log_returns.rolling(w).std() * np.sqrt(252)
        arr = vol.values

        for ci in candidate_indices:
            result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr

    return {"realized_vol": result}
