# %% component overview
# Long-only fixed-cash merger inventory, ranked by EV per unit of break loss and
# equalized by conservative break-loss contribution. The result is a sleeve-internal
# composition; the whole-book allocator owns the sleeve's capital multiplier.

import numpy as np

COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.cash_merger_break_risk",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": [
        "max_positions",
        "max_weight_multiple",
        "residual_entry_enabled",
        "residual_entry_threshold",
    ],
    "output_name": "target_weights",
    "consumes_outputs": [
        "deal_executable_price",
        "deal_expected_value",
        "deal_break_loss",
        "deal_eligible",
        "deal_residual",
        "deal_news",
    ],
    "defaults": {
        "max_positions": 0,
        "max_weight_multiple": 1.5,
        "residual_entry_enabled": False,
        "residual_entry_threshold": -0.02,
    },
    "owns_portfolio": False,
}


def lookback(**params):
    return 0


def _break_risk_weights(break_loss, positions, max_weight_multiple):
    selected = np.asarray(positions, dtype=int)
    weights = np.zeros(len(break_loss), dtype=float)
    if selected.size == 0:
        return weights

    cap = min(1.0, max_weight_multiple / float(selected.size))
    remaining = selected
    remaining_weight = 1.0
    while remaining.size:
        inverse_risk = 1.0 / break_loss[remaining]
        proposed = remaining_weight * inverse_risk / inverse_risk.sum()
        capped = proposed > cap
        if not capped.any():
            weights[remaining] = proposed
            break
        capped_positions = remaining[capped]
        weights[capped_positions] = cap
        remaining_weight -= cap * float(capped_positions.size)
        remaining = remaining[~capped]
    return weights


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit daily target weights for baseline and residual-entry variants."""

    periods = len(inputs.data.array("Close"))
    n_symbols = inputs.n_symbols
    expected_value = inputs.indicators["deal_expected_value"].reshape(
        periods, n_candidates, n_symbols
    )
    executable_price = inputs.indicators["deal_executable_price"].reshape(
        periods, n_candidates, n_symbols
    )
    break_loss = inputs.indicators["deal_break_loss"].reshape(
        periods, n_candidates, n_symbols
    )
    eligible = inputs.indicators["deal_eligible"].reshape(
        periods, n_candidates, n_symbols
    )
    residual = inputs.indicators["deal_residual"].reshape(
        periods, n_candidates, n_symbols
    )
    news = inputs.indicators["deal_news"].reshape(periods, n_candidates, n_symbols)
    result = np.zeros((periods, n_candidates, n_symbols), dtype=float)

    for candidate in range(n_candidates):
        max_positions = int(param_lists["max_positions"][candidate])
        max_weight_multiple = float(param_lists["max_weight_multiple"][candidate])
        residual_enabled = bool(param_lists["residual_entry_enabled"][candidate])
        residual_threshold = float(param_lists["residual_entry_threshold"][candidate])
        if max_positions < 0:
            raise ValueError("demeter.cash_merger_break_risk: max_positions cannot be negative")
        if max_weight_multiple < 1.0:
            raise ValueError(
                "demeter.cash_merger_break_risk: max_weight_multiple must be at least 1"
            )
        incumbent = np.zeros(n_symbols, dtype=bool)
        for row in range(periods):
            qualified = (
                (eligible[row, candidate] > 0.5)
                & np.isfinite(expected_value[row, candidate])
                & (expected_value[row, candidate] > 0.0)
                & np.isfinite(executable_price[row, candidate])
                & (executable_price[row, candidate] > 0.0)
                & np.isfinite(break_loss[row, candidate])
                & (break_loss[row, candidate] > 0.0)
            )
            incumbent &= qualified
            entrants = qualified & ~incumbent
            if residual_enabled:
                entrants &= (
                    np.isfinite(residual[row, candidate])
                    & (residual[row, candidate] <= residual_threshold)
                    & (news[row, candidate] < 0.5)
                )
            admitted = incumbent | entrants
            score = np.divide(
                expected_value[row, candidate],
                executable_price[row, candidate] * break_loss[row, candidate],
                out=np.full(n_symbols, -np.inf),
                where=admitted,
            )
            ordered = np.flatnonzero(admitted)[np.argsort(score[admitted])[::-1]]
            selected = ordered if max_positions == 0 else ordered[:max_positions]
            incumbent[:] = False
            incumbent[selected] = True
            result[row, candidate] = _break_risk_weights(
                break_loss[row, candidate],
                selected,
                max_weight_multiple,
            )
    return result.reshape(periods, n_candidates * n_symbols)
