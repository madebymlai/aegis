# %% component overview
# Duration-matched credit-carry selector. The active candidate keeps 50% in IG and
# 50% in HY, matches the static four-fund portfolio's contemporaneous duration, and
# tilts only within each quality bucket toward the larger excess-yield proxy.

import numpy as np

COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "demeter.credit_yield_proxy_selector",
    "version": "2.0.0",
    "input_names": ["Close"],
    "param_names": ["selection_strength"],
    "output_name": "target_weights",
    "consumes_outputs": [
        "credit_rebalance_due",
        "credit_excess_yield_proxy",
        "credit_modified_duration",
        "credit_data_fresh",
    ],
    "defaults": {"selection_strength": 1.0},
    "owns_portfolio": False,
}

_SHORT_IG = frozenset({"SDIG.LSEETF"})
_BROAD_IG = frozenset({"LQDE.LSEETF"})
_SHORT_HY = frozenset({"SDHY.LSEETF"})
_BROAD_HY = frozenset({"IHYU.LSEETF"})
_STATIC_WEIGHT = 0.25
_QUALITY_WEIGHT = 0.50
_MIN_FUND_WEIGHT = 0.05
_MAX_FUND_WEIGHT = 0.45
_TOLERANCE = 1e-10


def param_space():
    """Return exactly the static control and duration-matched active candidate."""
    from vectorbtpro import vbt

    return {"selection_strength": vbt.Param([0.0, 1.0])}


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


def _static_weights(n_symbols, roles):
    weights = np.zeros(n_symbols)
    weights[list(roles)] = _STATIC_WEIGHT
    return weights


def _within_bounds(value):
    return _MIN_FUND_WEIGHT - _TOLERANCE <= value <= _MAX_FUND_WEIGHT + _TOLERANCE


def _feasible_quality_weights(duration_deltas):
    """Return vertices for two within-quality tilts under one duration equality."""
    ig_delta, hy_delta = duration_deltas
    target = _STATIC_WEIGHT * (ig_delta + hy_delta)
    candidates = [(_STATIC_WEIGHT, _STATIC_WEIGHT)]

    if abs(hy_delta) > _TOLERANCE:
        for short_ig_weight in (_MIN_FUND_WEIGHT, _MAX_FUND_WEIGHT):
            short_hy_weight = (target - short_ig_weight * ig_delta) / hy_delta
            if _within_bounds(short_hy_weight):
                candidates.append((short_ig_weight, short_hy_weight))
    if abs(ig_delta) > _TOLERANCE:
        for short_hy_weight in (_MIN_FUND_WEIGHT, _MAX_FUND_WEIGHT):
            short_ig_weight = (target - short_hy_weight * hy_delta) / ig_delta
            if _within_bounds(short_ig_weight):
                candidates.append((short_ig_weight, short_hy_weight))
    if abs(ig_delta) <= _TOLERANCE and abs(hy_delta) <= _TOLERANCE:
        candidates.extend(
            (short_ig_weight, short_hy_weight)
            for short_ig_weight in (_MIN_FUND_WEIGHT, _MAX_FUND_WEIGHT)
            for short_hy_weight in (_MIN_FUND_WEIGHT, _MAX_FUND_WEIGHT)
        )
    return candidates


def _active_weights(excess_yield, duration, fresh, roles):
    static = _static_weights(len(excess_yield), roles)
    role_positions = list(roles)
    if not (
        np.isfinite(excess_yield[role_positions]).all()
        and np.isfinite(duration[role_positions]).all()
        and (fresh[role_positions] > 0.5).all()
    ):
        return static

    short_ig, broad_ig, short_hy, broad_hy = roles
    duration_deltas = (
        duration[short_ig] - duration[broad_ig],
        duration[short_hy] - duration[broad_hy],
    )
    candidates = _feasible_quality_weights(duration_deltas)

    def objective(candidate):
        short_ig_weight, short_hy_weight = candidate
        portfolio_proxy = (
            short_ig_weight * excess_yield[short_ig]
            + (_QUALITY_WEIGHT - short_ig_weight) * excess_yield[broad_ig]
            + short_hy_weight * excess_yield[short_hy]
            + (_QUALITY_WEIGHT - short_hy_weight) * excess_yield[broad_hy]
        )
        distance_from_static = abs(short_ig_weight - _STATIC_WEIGHT) + abs(
            short_hy_weight - _STATIC_WEIGHT
        )
        return portfolio_proxy, -distance_from_static

    short_ig_weight, short_hy_weight = max(candidates, key=objective)
    weights = np.zeros(len(excess_yield))
    weights[short_ig] = short_ig_weight
    weights[broad_ig] = _QUALITY_WEIGHT - short_ig_weight
    weights[short_hy] = short_hy_weight
    weights[broad_hy] = _QUALITY_WEIGHT - short_hy_weight
    return weights


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Emit monthly static-control or active duration-matched targets."""
    close = inputs.data.array("Close")
    columns = [str(column) for column in close.columns]
    roles = _role_indices(columns)
    periods = len(close)
    n_symbols = inputs.n_symbols
    due = inputs.indicators["credit_rebalance_due"].reshape(
        periods, n_candidates, n_symbols
    )
    excess_yield = inputs.indicators["credit_excess_yield_proxy"].reshape(
        periods, n_candidates, n_symbols
    )
    duration = inputs.indicators["credit_modified_duration"].reshape(
        periods, n_candidates, n_symbols
    )
    fresh = inputs.indicators["credit_data_fresh"].reshape(
        periods, n_candidates, n_symbols
    )
    result = np.full((periods, n_candidates, n_symbols), np.nan)

    for candidate in range(n_candidates):
        selection_strength = float(param_lists["selection_strength"][candidate])
        if selection_strength not in (0.0, 1.0):
            raise ValueError("selection_strength must be either 0.0 or 1.0")
        static = _static_weights(n_symbols, roles)
        for row in range(periods):
            if not (due[row, candidate] > 0.5).any():
                continue
            result[row, candidate] = (
                static
                if selection_strength == 0.0
                else _active_weights(
                    excess_yield[row, candidate],
                    duration[row, candidate],
                    fresh[row, candidate],
                    roles,
                )
            )
    return result.reshape(periods, n_candidates * n_symbols)
