# %% component overview
# Standalone one-name cat-bond sleeve. Artemis richness determines utilization within the
# budget assigned by Aegis Trader's Allocator. The monthly calendar is causal and NaN between
# decisions means hold, not daily drift correction.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.cat_bond_income",
    "version": "5.0.0",
    "input_names": ["Close"],
    "param_names": ["min_multiple"],
    "output_name": "target_weights",
    "consumes_outputs": [
        "rebalance_due",
        "cat_bond_net_carry",
        "cat_bond_risk_multiple",
        "cat_bond_richness",
        "cat_bond_data_fresh",
    ],
    "defaults": {
        "min_multiple": 2.0,
    },
    "owns_portfolio": False,
}


# %% parameter space
def param_space():
    """Return the minimum compensation required for sleeve inclusion."""

    from vectorbtpro import vbt

    return {"min_multiple": vbt.Param([2.0])}


# %% lookback
def lookback(**params):
    """No warmup beyond the consumed volatility Indicator."""
    return 0


# %% helpers
def _monthly_exposure(
    rebalance_due,
    loss_adjusted_yield,
    multiple,
    richness,
    fresh,
    min_multiple,
):
    """Size eligible CATB exposure by its trailing market-richness percentile."""

    if not np.isfinite(min_multiple) or min_multiple <= 0.0:
        raise ValueError("demeter.cat_bond_income: min_multiple must be finite and positive")
    qualifies = (
        (fresh > 0.5)
        & np.isfinite(loss_adjusted_yield)
        & (loss_adjusted_yield > 0.0)
        & np.isfinite(multiple)
        & (multiple >= min_multiple)
        & np.isfinite(richness)
    )
    decided = np.where(qualifies, np.clip(richness, 0.0, 1.0), 0.0)
    return np.where(rebalance_due > 0.5, decided, np.nan)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Build monthly cat-bond target weights for all candidates."""

    periods = len(inputs.data.array("Close"))
    n_symbols = inputs.n_symbols
    due = inputs.indicators["rebalance_due"].reshape(periods, n_candidates, n_symbols)
    net = inputs.indicators["cat_bond_net_carry"].reshape(periods, n_candidates, n_symbols)
    multiple = inputs.indicators["cat_bond_risk_multiple"].reshape(periods, n_candidates, n_symbols)
    richness = inputs.indicators["cat_bond_richness"].reshape(
        periods, n_candidates, n_symbols
    )
    fresh = inputs.indicators["cat_bond_data_fresh"].reshape(periods, n_candidates, n_symbols)
    result = np.full((periods, n_candidates, n_symbols), np.nan)
    for candidate in range(n_candidates):
        result[:, candidate, :] = _monthly_exposure(
            due[:, candidate, :],
            net[:, candidate, :],
            multiple[:, candidate, :],
            richness[:, candidate, :],
            fresh[:, candidate, :],
            float(param_lists["min_multiple"][candidate]),
        )
    return result.reshape(periods, n_candidates * n_symbols)
