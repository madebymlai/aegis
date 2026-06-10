# %% component overview
# Parameterized moving-average crossover strategy component.
# Emits a single allocation-native `active` frame consumed by the portfolio policy
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
    "param_space_callable": "param_space",
    "owns_portfolio": False,
    "wide_callable": "run_wide",
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
    target-allocation frame, applies the executable mask, gates it against
    `portfolio.gross_cap`, and writes the terminal-liquidation row.
    """

    close = inputs.data.feature("Close")
    return _active(close, int(fast_window), int(slow_window))


def _active(close, fast_window, slow_window):
    """Shared crossover formula for run and run_wide: one (rows, symbols) frame."""

    fast = close.rolling(fast_window, min_periods=1).mean()
    slow = close.rolling(slow_window, min_periods=1).mean()
    selected = fast.gt(slow)
    # 1.0 where selected this rebalance row, NaN where excluded.
    return selected.where(selected, other=float("nan")).astype(float)


# %% wide compute
def run_wide(inputs, *, n_candidates, **param_lists):
    """Vectorized crossover `active` blocks for all candidates in a single call.

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
    for ci in range(n_candidates):
        active = _active(close, int(fasts[ci]), int(slows[ci]))
        result[:, ci * n_symbols : (ci + 1) * n_symbols] = active.values
    return result
