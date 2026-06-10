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
    "param_space_callable": "param_space",
    "wide_callable": "run_wide",
}
COMPONENT_CALLABLE = "run"


# %% parameter space
def param_space():
    """Return VBT-native params for MA exploration."""

    return {
        "window": vbt.Param([10, 20, 50]),
        "wtype": vbt.Param(["simple", "exp"]),
    }


# %% main compute
def run(data, window, wtype):
    """Compute one moving-average frame for a single parameter row."""

    close = data.feature("Close")
    return _ma(close, int(window), str(wtype))


def _ma(close, window, wtype):
    """Shared MA formula for run and run_wide: one (rows, symbols) frame."""

    ma = vbt.MA.run(close, window=window, wtype=wtype).ma
    # Single param combo: restore plain symbol columns whether or not VBT
    # prepended param levels.
    ma.columns = close.columns
    return ma


# %% wide compute
def run_wide(data, *, n_candidates, **param_lists):
    """Vectorized MA for all candidates in a single call.

    Returns one candidate-major array of shape (rows, n_candidates * n_symbols):
    candidate ``ci`` owns the column block ``[ci * n_symbols, (ci + 1) * n_symbols)``.
    """

    close = data.feature("Close")
    n_symbols = len(close.columns)
    windows = param_lists["window"]
    wtypes = param_lists["wtype"]

    result = np.full((len(close), n_candidates * n_symbols), np.nan)
    for window, wtype in set(zip(windows, wtypes, strict=True)):
        arr = _ma(close, int(window), str(wtype)).values
        for ci in range(n_candidates):
            if windows[ci] == window and wtypes[ci] == wtype:
                result[:, ci * n_symbols : (ci + 1) * n_symbols] = arr
    return result
