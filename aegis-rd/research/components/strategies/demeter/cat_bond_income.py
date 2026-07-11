# %% component overview
# Standalone Demeter cat-bond income sleeve. It owns one executable UCITS ETF and sizes it
# from market carry richness, capped by a survivable fixed capital share. The
# monthly calendar is causal and NaN between decisions means hold, not daily drift correction.
# There is no corporate-credit richness input: catastrophe insurance is a distinct premium.

# %% imports
import numpy as np

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.cat_bond_income",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["min_weight", "max_weight", "low_richness", "high_richness"],
    "output_name": "target_weights",
    "consumes_outputs": ["rebalance_due", "cat_bond_net_carry", "cat_bond_richness", "cat_bond_data_fresh"],
    "defaults": {"min_weight": 0.05, "max_weight": 0.25, "low_richness": 0.2, "high_richness": 0.8},
    "owns_portfolio": False,
}

# %% parameter space
def param_space():
    """Return the narrow pilot grid over risk target and capital budget."""

    from vectorbtpro import vbt

    return {
        "max_weight": vbt.Param([0.15, 0.20, 0.25]),
        "min_weight": vbt.Param([0.05]),
        "low_richness": vbt.Param([0.2]),
        "high_richness": vbt.Param([0.8]),
    }


# %% lookback
def lookback(**params):
    """No warmup beyond the consumed volatility Indicator."""
    return 0


# %% helpers
def _monthly_weight(rebalance_due, net_carry, richness, fresh, min_weight, max_weight, low, high):
    """Map market richness monotonically into the permitted capital interval."""

    if not 0.0 < max_weight <= 1.0:
        raise ValueError("demeter.cat_bond_income: max_weight must be in (0, 1]")
    if not 0.0 <= min_weight <= max_weight or high <= low:
        raise ValueError("demeter.cat_bond_income: invalid richness sizing interval")
    score = np.clip((richness - low) / (high - low), 0.0, 1.0)
    target = min_weight + score * (max_weight - min_weight)
    usable = np.isfinite(richness) & (net_carry > 0.0) & (fresh > 0.5)
    return np.where(rebalance_due > 0.5, np.where(usable, target, 0.0), np.nan)


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Build monthly cat-bond target weights for all candidates."""

    periods = len(inputs.data.array("Close"))
    n_symbols = inputs.n_symbols
    due = inputs.indicators["rebalance_due"].reshape(periods, n_candidates, n_symbols)
    net = inputs.indicators["cat_bond_net_carry"].reshape(periods, n_candidates, n_symbols)
    richness = inputs.indicators["cat_bond_richness"].reshape(periods, n_candidates, n_symbols)
    fresh = inputs.indicators["cat_bond_data_fresh"].reshape(periods, n_candidates, n_symbols)
    result = np.full((periods, n_candidates, n_symbols), np.nan)
    for candidate in range(n_candidates):
        result[:, candidate, :] = _monthly_weight(
            due[:, candidate, :],
            net[:, candidate, :], richness[:, candidate, :], fresh[:, candidate, :],
            float(param_lists["min_weight"][candidate]),
            float(param_lists["max_weight"][candidate]),
            float(param_lists["low_richness"][candidate]),
            float(param_lists["high_richness"][candidate]),
        )
    return result.reshape(periods, n_candidates * n_symbols)
