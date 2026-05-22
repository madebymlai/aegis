# %% component overview
# Parameterized moving-average crossover strategy component.
# Source: run-provided Close feature and centrally configured Aegis portfolio settings.

# %% imports
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "example.ma_cross",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["fast_window", "slow_window"],
    "signal_outputs": ["entries", "exits"],
    "defaults": {"fast_window": 10, "slow_window": 20},
    "param_space_callable": "param_space",
    "owns_portfolio": False,
}
COMPONENT_CALLABLE = "run"


# %% parameter space
def param_space():
    """Return VBT-native params for moving-average crossover exploration."""

    return {
        "fast_window": vbt.Param([5, 10, 20]),
        "slow_window": vbt.Param([30, 50, 100]),
    }


# %% main compute
def run(inputs, fast_window, slow_window):
    """Emit entries/exits for one moving-average parameter row."""

    close = inputs.data.feature("Close")
    fast = close.rolling(int(fast_window), min_periods=1).mean()
    slow = close.rolling(int(slow_window), min_periods=1).mean()
    return {
        "entries": fast.gt(slow).fillna(False),
        "exits": fast.lt(slow).fillna(False),
    }
