# %% component overview
# Monthly decision calendar for the Demeter cat-bond income sleeve. The first observed bar
# in each selected month is executable without knowing the future month-end. The Strategy
# consumes the mask and emits NaN between decisions so the held book drifts without daily
# target-percent correction.

# %% imports
import numpy as np
import pandas as pd

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.cat_bond_calendar",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["rebalance_interval_months"],
    "output_names": ["rebalance_due"],
    "defaults": {"rebalance_interval_months": 1},
}


# %% parameter space
def param_space():
    """Return the fixed monthly decision interval."""

    from vectorbtpro import vbt

    return {"rebalance_interval_months": vbt.Param([1])}


# %% lookback
def lookback(**params):
    """The calendar has no price-history warmup."""
    return 0


# %% helpers
def _rebalance_due(index, interval_months):
    """Mark the first observed row of every selected calendar month."""

    if interval_months < 1:
        raise ValueError("demeter.cat_bond_calendar: rebalance_interval_months must be >= 1")
    months = pd.PeriodIndex(index, freq="M")
    month_start = np.r_[True, months[1:] != months[:-1]]
    ordinal = months.astype("int64")
    selected = (ordinal - ordinal[0]) % interval_months == 0
    return (month_start & selected).astype(float)


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Build a candidate-major monthly decision mask for every symbol."""

    close = data.array("Close")
    periods = len(close)
    n_symbols = len(close.columns)
    result = np.zeros((periods, n_candidates * n_symbols), dtype=float)
    for candidate, interval in enumerate(param_lists["rebalance_interval_months"]):
        due = _rebalance_due(close.index, int(interval))
        start = candidate * n_symbols
        result[:, start : start + n_symbols] = due[:, None]
    return {"rebalance_due": result}
