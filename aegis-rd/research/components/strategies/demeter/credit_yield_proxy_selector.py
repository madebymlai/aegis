# %% component overview
# Sparse, full-budget credit-yield selector. One IG and one HY bucket are always held;
# selection changes maturity within quality and never becomes a credit-quality timing gate.

import itertools

import numpy as np

COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.credit_yield_proxy_selector",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": [
        "selection_strength",
        "high_yield_weight",
        "duration_penalty_bps",
        "max_modified_duration",
    ],
    "output_name": "target_weights",
    "consumes_outputs": [
        "credit_rebalance_due",
        "credit_net_ytw",
        "credit_modified_duration",
        "credit_data_fresh",
    ],
    "defaults": {
        "selection_strength": 1.0,
        "high_yield_weight": 0.5,
        "duration_penalty_bps": 10.0,
        "max_modified_duration": 6.0,
    },
    "owns_portfolio": False,
}

_SHORT_IG = frozenset({"SDIG.LSEETF"})
_BROAD_IG = frozenset({"LQDE.LSEETF"})
_SHORT_HY = frozenset({"SDHY.LSEETF"})
_BROAD_HY = frozenset({"IHYU.LSEETF"})


def param_space():
    """Return one static control plus six coupled active configurations."""
    from vectorbtpro import vbt

    return {
        "selection_strength": vbt.Param([0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], level=0),
        "high_yield_weight": vbt.Param([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5], level=0),
        "duration_penalty_bps": vbt.Param(
            [0.0, 0.0, 0.0, 10.0, 10.0, 25.0, 25.0], level=0
        ),
        "max_modified_duration": vbt.Param([6.0, 4.0, 6.0, 4.0, 6.0, 4.0, 6.0], level=0),
    }


def lookback(**params):
    return 0


def _single_index(columns, role, names):
    matches = [index for index, column in enumerate(columns) if column in names]
    if len(matches) != 1:
        raise ValueError(
            f"demeter.credit_yield_proxy_selector: expected one {role} bucket, found {len(matches)}"
        )
    return matches[0]


def _role_indices(columns):
    return (
        _single_index(columns, "short IG", _SHORT_IG),
        _single_index(columns, "broad IG", _BROAD_IG),
        _single_index(columns, "short HY", _SHORT_HY),
        _single_index(columns, "broad HY", _BROAD_HY),
    )


def _validate_params(selection_strength, high_yield_weight, duration_penalty_bps, max_duration):
    if selection_strength not in (0.0, 1.0):
        raise ValueError("selection_strength must be either 0.0 or 1.0")
    if not np.isfinite(high_yield_weight) or not 0.0 < high_yield_weight < 1.0:
        raise ValueError("high_yield_weight must be finite and strictly between zero and one")
    if not np.isfinite(duration_penalty_bps) or duration_penalty_bps < 0.0:
        raise ValueError("duration_penalty_bps must be finite and non-negative")
    if not np.isfinite(max_duration) or max_duration <= 0.0:
        raise ValueError("max_modified_duration must be finite and positive")


def _static_weights(n_symbols, broad_ig, broad_hy, high_yield_weight):
    weights = np.zeros(n_symbols)
    weights[broad_ig] = 1.0 - high_yield_weight
    weights[broad_hy] = high_yield_weight
    return weights


def _active_weights(
    ytw,
    duration,
    fresh,
    roles,
    high_yield_weight,
    duration_penalty_bps,
    max_duration,
):
    short_ig, broad_ig, short_hy, broad_hy = roles
    if not (
        np.isfinite(ytw[list(roles)]).all()
        and np.isfinite(duration[list(roles)]).all()
        and (fresh[list(roles)] > 0.5).all()
    ):
        return _static_weights(len(ytw), broad_ig, broad_hy, high_yield_weight)

    ig_weight = 1.0 - high_yield_weight
    penalty = duration_penalty_bps / 100.0
    candidates = []
    for ig, hy in itertools.product((short_ig, broad_ig), (short_hy, broad_hy)):
        portfolio_duration = ig_weight * duration[ig] + high_yield_weight * duration[hy]
        adjusted_yield = (
            ig_weight * (ytw[ig] - penalty * duration[ig])
            + high_yield_weight * (ytw[hy] - penalty * duration[hy])
        )
        candidates.append((portfolio_duration <= max_duration, adjusted_yield, -portfolio_duration, ig, hy))
    feasible = [candidate for candidate in candidates if candidate[0]]
    selected = (
        max(feasible, key=lambda candidate: candidate[1:3])
        if feasible
        else max(candidates, key=lambda candidate: candidate[2])
    )
    weights = np.zeros(len(ytw))
    weights[selected[3]] = ig_weight
    weights[selected[4]] = high_yield_weight
    return weights


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit monthly static-control or active credit-bucket targets for all candidates."""
    close = inputs.data.array("Close")
    columns = [str(column) for column in close.columns]
    roles = _role_indices(columns)
    periods = len(close)
    n_symbols = inputs.n_symbols
    due = inputs.indicators["credit_rebalance_due"].reshape(
        periods, n_candidates, n_symbols
    )
    ytw = inputs.indicators["credit_net_ytw"].reshape(periods, n_candidates, n_symbols)
    duration = inputs.indicators["credit_modified_duration"].reshape(
        periods, n_candidates, n_symbols
    )
    fresh = inputs.indicators["credit_data_fresh"].reshape(
        periods, n_candidates, n_symbols
    )
    result = np.full((periods, n_candidates, n_symbols), np.nan)

    for candidate in range(n_candidates):
        selection_strength = float(param_lists["selection_strength"][candidate])
        high_yield_weight = float(param_lists["high_yield_weight"][candidate])
        duration_penalty_bps = float(param_lists["duration_penalty_bps"][candidate])
        max_duration = float(param_lists["max_modified_duration"][candidate])
        _validate_params(
            selection_strength,
            high_yield_weight,
            duration_penalty_bps,
            max_duration,
        )
        static = _static_weights(n_symbols, roles[1], roles[3], high_yield_weight)
        for row in range(periods):
            if not (due[row, candidate] > 0.5).any():
                continue
            if selection_strength == 0.0:
                result[row, candidate] = static
                continue
            result[row, candidate] = _active_weights(
                ytw[row, candidate],
                duration[row, candidate],
                fresh[row, candidate],
                roles,
                high_yield_weight,
                duration_penalty_bps,
                max_duration,
            )
    return result.reshape(periods, n_candidates * n_symbols)
