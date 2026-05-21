# %% component overview
# Fixed moving-average indicator component promoted from an explored playbook idea.
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
}
COMPONENT_CALLABLE = "run"


# %% main compute
def run(data):
    """Compute one fixed simple moving average over Close for component use."""

    ma = vbt.MA.run(
        data.feature("Close"),
        window=20,
        wtype="simple",
        hide_params=None,
        hide_default=False,
    )
    return ma.ma
