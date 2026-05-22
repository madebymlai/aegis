# %% component overview
# Parameterized moving-average crossover strategy component.
# Emits a single allocation-native `active` frame consumed by the portfolio policy
# layer; portfolio sizing, direction, and timing remain centrally configured.

# %% imports
from vectorbtpro import vbt

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "example.ma_cross",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["fast_window", "slow_window"],
    "output_name": "active",
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
    """Return one `active` frame for the moving-average parameter row.

    Selection convention: non-NaN cells = selected this rebalance row, NaN = excluded.
    The portfolio policy layer converts the `active` frame to a validated
    target-allocation frame, applies the executable mask, normalizes against
    `portfolio.target_exposure_cap`, and writes the terminal-liquidation row.
    """

    close = inputs.data.feature("Close")
    fast = close.rolling(int(fast_window), min_periods=1).mean()
    slow = close.rolling(int(slow_window), min_periods=1).mean()
    selected = fast.gt(slow)
    # 1.0 where selected this rebalance row, NaN where excluded.
    return selected.where(selected, other=float("nan")).astype(float)
