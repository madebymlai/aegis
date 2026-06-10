# %% component overview
# Parameterized moving-average crossover strategy component.
# Emits a single allocation-native `active` array consumed by the allocation policy
# layer; portfolio sizing, direction, and timing remain centrally configured.

# %% imports
import numpy as np
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
    "owns_portfolio": False,
}


# %% parameter space
def param_space():
    """Return VBT-native params for moving-average crossover exploration."""

    return {
        "fast_window": vbt.Param([5, 10, 20]),
        "slow_window": vbt.Param([30, 50, 100]),
    }


# %% helpers
def _active(close, fast_window, slow_window):
    """Compute one active-allocation frame for one parameter row."""

    fast = close.rolling(fast_window, min_periods=1).mean()
    slow = close.rolling(slow_window, min_periods=1).mean()
    selected = fast.gt(slow)
    # 1.0 where selected this rebalance row, NaN where excluded.
    return selected.where(selected, other=float("nan")).astype(float)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Compute candidate-major crossover allocations for all candidates.

    Indicator inputs (none here) arrive as candidate-major arrays under
    ``inputs.indicators[output_name]``. The return value uses the same layout:
    shape (rows, n_candidates * n_symbols), candidate ``ci`` owning the column
    block ``[ci * n_symbols, (ci + 1) * n_symbols)``.
    """

    close = inputs.data.feature("Close")
    n_symbols = inputs.n_symbols
    fasts = param_lists["fast_window"]
    slows = param_lists["slow_window"]

    result = np.full((len(close), n_candidates * n_symbols), np.nan)
    for candidate_index in range(n_candidates):
        active = _active(close, int(fasts[candidate_index]), int(slows[candidate_index]))
        cols = slice(
            candidate_index * n_symbols,
            (candidate_index + 1) * n_symbols,
        )
        result[:, cols] = active.values
    return result
