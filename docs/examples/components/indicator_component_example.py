# %% component overview
# Parameterized moving-average indicator component.
# Source: VectorBT PRO MA over the run-provided Close feature.

# %% imports
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
}
COMPONENT_CALLABLE = "run"


# %% parameter space
def param_space():
    """Return VBT-native params for MA exploration."""

    return {
        "window": vbt.Param([10, 20, 50]),
        "wtype": vbt.Param(["simple", "exponential"]),
    }


# %% main compute
def run(data, window, wtype):
    """Compute one moving-average output for a VBT parameter row."""

    ma = vbt.MA.run(
        data.feature("Close"),
        window=window,
        wtype=wtype,
        hide_params=None,
        hide_default=False,
    )
    return ma.ma
