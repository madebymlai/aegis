# %% component overview
# Parameterized moving-average indicator component.
# Source: VectorBT PRO MA over the run-provided Close feature.

# %% imports
import numpy as np
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "example.ma",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["window", "wtype"],
    "output_names": ["ma"],
    "defaults": {"window": 20, "wtype": "simple"},
}


# %% parameter space
def param_space():
    """Return VBT-native params for MA exploration."""

    return {
        "window": vbt.Param([10, 20, 50]),
        "wtype": vbt.Param(["simple", "exp"]),
    }


# %% helpers
def _ma(close, window, wtype):
    """Compute one moving-average frame for a single parameter row."""

    ma = vbt.MA.run(close, window=window, wtype=wtype).ma
    # Single param combo: restore plain symbol columns whether or not VBT
    # prepended param levels.
    ma.columns = close.columns
    return ma


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Compute candidate-major moving-average output for all candidates."""

    close = data.feature("Close")
    n_symbols = len(close.columns)
    windows = param_lists["window"]
    wtypes = param_lists["wtype"]

    result = np.full((len(close), n_candidates * n_symbols), np.nan)
    for window, wtype in set(zip(windows, wtypes, strict=True)):
        arr = _ma(close, int(window), str(wtype)).values
        for candidate_index in range(n_candidates):
            if windows[candidate_index] == window and wtypes[candidate_index] == wtype:
                cols = slice(
                    candidate_index * n_symbols,
                    (candidate_index + 1) * n_symbols,
                )
                result[:, cols] = arr
    return {"ma": result}
