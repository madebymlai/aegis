"""Pure covariance-aware risk-budget allocator.

The allocator owns the Trader-side risk-budget scaling seam: raw per-sleeve
weights from Execution Bundles in, risk-budget-scaled per-sleeve weights out.
It imports no Nautilus types.  The diagonal allocator from the tracer slice is
kept as the zero-correlation limit; the covariance path uses Equal Risk
Contribution (ERC) and can split risk top-down by declared risk group before
allocating within each group.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

from aegis_trader.domain.book_config import DrawdownDeleverCurve
from aegis_trader.domain.types import SleeveName

_EPS = 1e-12
_ERC_TOLERANCE = 1e-10
_ERC_MAX_ITERATIONS = 10_000

NameT = TypeVar("NameT", bound=Hashable)


@dataclass(frozen=True)
class Allocation:
    """Risk-budget-scaled sleeve targets and their scalar multipliers."""

    multipliers: Mapping[SleeveName, float]
    scaled_targets: Mapping[SleeveName, Mapping[str, float]]


@dataclass(frozen=True)
class _GroupComposition:
    """Within-group ERC composition in member order."""

    members: tuple[SleeveName, ...]
    weights: np.ndarray


def allocate_diagonal_vol_target(
    *,
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    risk_shares: Mapping[SleeveName, float],
    realized_vols: Mapping[SleeveName, float] | None,
    book_vol_target: float,
    realized_drawdown: float | None = None,
    drawdown_delever_curve: DrawdownDeleverCurve | None = None,
) -> Allocation:
    """Scale per-sleeve target weights to realize a diagonal risk budget.

    During warmup callers pass ``realized_vols=None`` and the allocator falls
    back to raw risk shares.  Once a vol estimate is supplied, every active
    sleeve with positive risk share must have a finite, positive volatility;
    missing or degenerate estimates fail closed rather than silently mis-sizing.
    """
    _validate_book_vol_target(book_vol_target)

    active = _active_sleeves(sleeve_targets, risk_shares)
    if not active:
        return Allocation(multipliers={}, scaled_targets={})
    if realized_vols is None:
        return _delevered_allocation(
            sleeve_targets,
            _risk_share_multipliers(active, risk_shares),
            realized_drawdown=realized_drawdown,
            curve=drawdown_delever_curve,
        )

    vols = _validate_vols(active, realized_vols)
    raw = {
        name: float(risk_shares[name]) * book_vol_target / vols[name]
        for name in active
    }
    raw_vol = diagonal_book_vol(raw, vols)
    if raw_vol <= _EPS or not math.isfinite(raw_vol):
        raise ValueError("diagonal allocation produced degenerate book vol")

    scale = book_vol_target / raw_vol
    multipliers = {name: multiplier * scale for name, multiplier in raw.items()}
    return _delevered_allocation(
        sleeve_targets,
        multipliers,
        realized_drawdown=realized_drawdown,
        curve=drawdown_delever_curve,
    )


def allocate_covariance_vol_target(
    *,
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    risk_shares: Mapping[SleeveName, float],
    realized_covariance: Mapping[SleeveName, Mapping[SleeveName, float]] | None,
    book_vol_target: float,
    groups: Mapping[SleeveName, Hashable] | None = None,
    realized_drawdown: float | None = None,
    drawdown_delever_curve: DrawdownDeleverCurve | None = None,
) -> Allocation:
    """Scale per-sleeve target weights using covariance-aware ERC/HRP.

    ``risk_shares`` are the same operator-facing shares as the diagonal tracer:
    in the zero-correlation case capital multipliers are proportional to
    ``risk_share / volatility``.  Internally, ERC variance budgets are therefore
    the squared risk shares normalized to one, which makes the covariance-aware
    solver's diagonal limit exactly reproduce ``allocate_diagonal_vol_target``.

    When ``groups`` is supplied, risk is allocated top-down: ERC across groups
    using group shares, then ERC within each group.  This is the HRP seam that
    prevents a correlated cluster with many sleeves from dominating the book.
    """
    _validate_book_vol_target(book_vol_target)

    active = _active_sleeves(sleeve_targets, risk_shares)
    if not active:
        return Allocation(multipliers={}, scaled_targets={})
    if realized_covariance is None:
        return _delevered_allocation(
            sleeve_targets,
            _risk_share_multipliers(active, risk_shares),
            realized_drawdown=realized_drawdown,
            curve=drawdown_delever_curve,
        )

    covariance = _covariance_matrix(active, realized_covariance)
    composition = _composition_vector(
        active=active,
        covariance=covariance,
        risk_shares=risk_shares,
        groups=groups,
    )

    composition_by_name = {
        name: float(weight) for name, weight in zip(active, composition, strict=True)
    }
    composition_vol = covariance_book_vol(composition_by_name, realized_covariance)
    if composition_vol <= _EPS or not math.isfinite(composition_vol):
        raise ValueError("covariance allocation produced degenerate book vol")

    scale = book_vol_target / composition_vol
    multipliers = {
        name: multiplier * scale
        for name, multiplier in composition_by_name.items()
    }
    return _delevered_allocation(
        sleeve_targets,
        multipliers,
        realized_drawdown=realized_drawdown,
        curve=drawdown_delever_curve,
    )


def equal_risk_contribution_weights(
    covariance: Mapping[NameT, Mapping[NameT, float]],
    risk_shares: Mapping[NameT, float] | None = None,
) -> dict[NameT, float]:
    """Return long-only ERC composition weights that sum to one.

    This generic helper is the pure default for a multi-name sleeve.  If no
    shares are supplied, every name receives equal risk.  If shares are supplied,
    their diagonal-limit interpretation matches the book allocator:
    zero-correlation weights are proportional to ``share / volatility``.
    """
    names = tuple(covariance.keys())
    if not names:
        return {}
    matrix = _generic_covariance_matrix(names, covariance)
    shares = [
        1.0 if risk_shares is None else float(risk_shares[name])
        for name in names
    ]
    weights = _risk_budgeted_composition(matrix, shares)
    return {name: float(weight) for name, weight in zip(names, weights, strict=True)}


def diagonal_book_vol(
    multipliers: Mapping[SleeveName, float],
    realized_vols: Mapping[SleeveName, float],
) -> float:
    """Return the diagonal book volatility for sleeve multipliers and vols."""
    variance = 0.0
    for name, multiplier in multipliers.items():
        vol = float(realized_vols[name])
        variance += (float(multiplier) * vol) ** 2
    return math.sqrt(variance)


def covariance_book_vol(
    multipliers: Mapping[NameT, float],
    realized_covariance: Mapping[NameT, Mapping[NameT, float]],
) -> float:
    """Return book volatility for weights/multipliers and a covariance matrix."""
    if not multipliers:
        return 0.0
    names = tuple(multipliers.keys())
    matrix = _generic_covariance_matrix(names, realized_covariance)
    weights = np.array([float(multipliers[name]) for name in names], dtype=float)
    variance = float(weights @ matrix @ weights)
    if variance < -_EPS:
        raise ValueError(f"covariance produced negative variance: {variance!r}")
    return math.sqrt(max(variance, 0.0))


def risk_contribution_shares(
    multipliers: Mapping[NameT, float],
    realized_covariance: Mapping[NameT, Mapping[NameT, float]],
) -> dict[NameT, float]:
    """Return each name's variance risk-contribution share."""
    if not multipliers:
        return {}
    names = tuple(multipliers.keys())
    matrix = _generic_covariance_matrix(names, realized_covariance)
    weights = np.array([float(multipliers[name]) for name in names], dtype=float)
    marginal = matrix @ weights
    variance = float(weights @ marginal)
    if variance <= _EPS or not math.isfinite(variance):
        raise ValueError("cannot compute risk contributions for degenerate book")
    contributions = weights * marginal / variance
    return {name: float(rc) for name, rc in zip(names, contributions, strict=True)}


def _validate_book_vol_target(book_vol_target: float) -> None:
    if book_vol_target <= 0 or not math.isfinite(book_vol_target):
        raise ValueError(f"book_vol_target must be positive, got {book_vol_target!r}")


def _delevered_allocation(
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    multipliers: Mapping[SleeveName, float],
    *,
    realized_drawdown: float | None,
    curve: DrawdownDeleverCurve | None,
) -> Allocation:
    return _allocation_from_multipliers(
        sleeve_targets,
        _apply_drawdown_delever(
            multipliers,
            realized_drawdown=realized_drawdown,
            curve=curve,
        ),
    )


def _apply_drawdown_delever(
    multipliers: Mapping[SleeveName, float],
    *,
    realized_drawdown: float | None,
    curve: DrawdownDeleverCurve | None,
) -> dict[SleeveName, float]:
    if curve is None:
        return {name: float(multiplier) for name, multiplier in multipliers.items()}

    drawdown = 0.0 if realized_drawdown is None else realized_drawdown
    exposure_multiplier = curve.multiplier_for(drawdown)
    return {
        name: float(multiplier) * exposure_multiplier
        for name, multiplier in multipliers.items()
    }


def _risk_share_multipliers(
    active: tuple[SleeveName, ...],
    risk_shares: Mapping[SleeveName, float],
) -> dict[SleeveName, float]:
    return {name: float(risk_shares[name]) for name in active}


def _allocation_from_multipliers(
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    multipliers: Mapping[SleeveName, float],
) -> Allocation:
    return Allocation(
        multipliers=multipliers,
        scaled_targets=_scale_targets(sleeve_targets, multipliers),
    )


def _active_sleeves(
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    risk_shares: Mapping[SleeveName, float],
) -> tuple[SleeveName, ...]:
    active: list[SleeveName] = []
    for name, targets in sleeve_targets.items():
        share = float(risk_shares.get(name, 0.0))
        if share < -_EPS or not math.isfinite(share):
            raise ValueError(
                f"risk share for sleeve {name.value!r} must be finite and non-negative"
            )
        if share <= _EPS:
            continue
        if any(abs(float(weight)) > _EPS for weight in targets.values()):
            active.append(name)
    return tuple(active)


def _validate_vols(
    active: tuple[SleeveName, ...],
    realized_vols: Mapping[SleeveName, float],
) -> dict[SleeveName, float]:
    vols: dict[SleeveName, float] = {}
    for name in active:
        if name not in realized_vols:
            raise ValueError(f"missing realized vol for sleeve {name.value!r}")
        vol = float(realized_vols[name])
        if vol <= _EPS or not math.isfinite(vol):
            raise ValueError(
                f"degenerate realized vol for sleeve {name.value!r}: {vol!r}"
            )
        vols[name] = vol
    return vols


def _covariance_matrix(
    active: tuple[SleeveName, ...],
    realized_covariance: Mapping[SleeveName, Mapping[SleeveName, float]],
) -> np.ndarray:
    try:
        return _generic_covariance_matrix(active, realized_covariance)
    except KeyError as exc:
        missing = exc.args[0]
        label = missing.value if isinstance(missing, SleeveName) else str(missing)
        raise ValueError(f"missing realized covariance for sleeve {label!r}") from exc


def _generic_covariance_matrix(
    names: tuple[NameT, ...],
    covariance: Mapping[NameT, Mapping[NameT, float]],
) -> np.ndarray:
    matrix = np.empty((len(names), len(names)), dtype=float)
    for i, row_name in enumerate(names):
        row = covariance[row_name]
        for j, col_name in enumerate(names):
            value = float(row[col_name])
            if not math.isfinite(value):
                raise ValueError("realized covariance entries must be finite")
            matrix[i, j] = value
    for i, name in enumerate(names):
        diag = matrix[i, i]
        if diag <= _EPS:
            raise ValueError(
                f"degenerate realized variance for {str(name)!r}: {diag!r}"
            )
    if not np.allclose(matrix, matrix.T, rtol=1e-8, atol=1e-12):
        raise ValueError("realized covariance matrix must be symmetric")
    return matrix


def _composition_vector(
    *,
    active: tuple[SleeveName, ...],
    covariance: np.ndarray,
    risk_shares: Mapping[SleeveName, float],
    groups: Mapping[SleeveName, Hashable] | None,
) -> np.ndarray:
    if groups is None:
        shares = [risk_shares[name] for name in active]
        return _risk_budgeted_composition(covariance, shares)
    return _hierarchical_composition(active, covariance, risk_shares, groups)


def _hierarchical_composition(
    active: tuple[SleeveName, ...],
    covariance: np.ndarray,
    risk_shares: Mapping[SleeveName, float],
    groups: Mapping[SleeveName, Hashable],
) -> np.ndarray:
    active_index = {name: i for i, name in enumerate(active)}
    grouped = _group_active_sleeves(active, groups)
    within = _within_group_compositions(
        grouped,
        active_index,
        covariance,
        risk_shares,
    )
    group_names = tuple(grouped.keys())
    group_covariance = _group_covariance_matrix(
        group_names,
        within,
        active_index,
        covariance,
    )
    group_shares = _group_risk_shares(group_names, grouped, risk_shares)
    group_weights = _risk_budgeted_composition(group_covariance, group_shares)

    composition = np.zeros(len(active), dtype=float)
    for group_weight, group_name in zip(group_weights, group_names, strict=True):
        group_composition = within[group_name]
        for member_weight, member in zip(
            group_composition.weights,
            group_composition.members,
            strict=True,
        ):
            composition[active_index[member]] = group_weight * member_weight
    return composition / float(composition.sum())


def _group_active_sleeves(
    active: tuple[SleeveName, ...],
    groups: Mapping[SleeveName, Hashable],
) -> dict[Hashable, tuple[SleeveName, ...]]:
    grouped: dict[Hashable, list[SleeveName]] = {}
    for name in active:
        group = groups.get(name)
        if group is None:
            raise ValueError(f"missing risk group for sleeve {name.value!r}")
        grouped.setdefault(group, []).append(name)
    return {group: tuple(members) for group, members in grouped.items()}


def _within_group_compositions(
    grouped: Mapping[Hashable, tuple[SleeveName, ...]],
    active_index: Mapping[SleeveName, int],
    covariance: np.ndarray,
    risk_shares: Mapping[SleeveName, float],
) -> dict[Hashable, _GroupComposition]:
    return {
        group: _GroupComposition(
            members=members,
            weights=_risk_budgeted_composition(
                _sub_covariance(covariance, members, members, active_index),
                [risk_shares[name] for name in members],
            ),
        )
        for group, members in grouped.items()
    }


def _group_covariance_matrix(
    group_names: tuple[Hashable, ...],
    within: Mapping[Hashable, _GroupComposition],
    active_index: Mapping[SleeveName, int],
    covariance: np.ndarray,
) -> np.ndarray:
    group_covariance = np.empty((len(group_names), len(group_names)), dtype=float)
    for i, left_group in enumerate(group_names):
        left = within[left_group]
        for j, right_group in enumerate(group_names):
            right = within[right_group]
            block = _sub_covariance(
                covariance,
                left.members,
                right.members,
                active_index,
            )
            group_covariance[i, j] = float(left.weights @ block @ right.weights)
    return group_covariance


def _sub_covariance(
    covariance: np.ndarray,
    rows: tuple[SleeveName, ...],
    columns: tuple[SleeveName, ...],
    active_index: Mapping[SleeveName, int],
) -> np.ndarray:
    row_indices = [active_index[name] for name in rows]
    column_indices = [active_index[name] for name in columns]
    return covariance[np.ix_(row_indices, column_indices)]


def _group_risk_shares(
    group_names: tuple[Hashable, ...],
    grouped: Mapping[Hashable, tuple[SleeveName, ...]],
    risk_shares: Mapping[SleeveName, float],
) -> list[float]:
    return [
        sum(float(risk_shares[name]) for name in grouped[group])
        for group in group_names
    ]


def _risk_budgeted_composition(
    covariance: np.ndarray,
    risk_shares: list[float],
) -> np.ndarray:
    return _erc_vector(covariance, _variance_budgets(risk_shares))


def _variance_budgets(risk_shares: list[float]) -> np.ndarray:
    shares = np.array(risk_shares, dtype=float)
    if np.any(~np.isfinite(shares)) or np.any(shares < -_EPS):
        raise ValueError("risk shares must be finite and non-negative")
    if np.any(shares <= _EPS):
        raise ValueError("active ERC names must have positive risk shares")
    squared = shares * shares
    total = float(squared.sum())
    if total <= _EPS:
        raise ValueError("ERC risk budget must be positive")
    return squared / total


def _erc_vector(covariance: np.ndarray, variance_budgets: np.ndarray) -> np.ndarray:
    size = covariance.shape[0]
    if size == 0:
        return np.array([], dtype=float)
    if size == 1:
        return np.array([1.0], dtype=float)

    vols = np.sqrt(np.diag(covariance))
    weights = np.sqrt(variance_budgets) / vols
    weights = weights / float(weights.sum())

    for _ in range(_ERC_MAX_ITERATIONS):
        previous = weights.copy()
        marginal = covariance @ weights
        variance = float(weights @ marginal)
        if variance <= _EPS or not math.isfinite(variance):
            raise ValueError("ERC solve produced degenerate variance")
        target_contributions = variance_budgets * variance

        for index in range(size):
            own_variance = float(covariance[index, index])
            cross = float(covariance[index] @ weights - own_variance * weights[index])
            target = float(target_contributions[index])
            discriminant = cross * cross + 4.0 * own_variance * target
            if discriminant < 0.0 or not math.isfinite(discriminant):
                raise ValueError("ERC solve failed on covariance matrix")
            weights[index] = max(
                (-cross + math.sqrt(discriminant)) / (2.0 * own_variance),
                _EPS,
            )

        weights = weights / float(weights.sum())
        if np.max(np.abs(weights - previous)) <= _ERC_TOLERANCE:
            marginal = covariance @ weights
            variance = float(weights @ marginal)
            contributions = weights * marginal / variance
            if np.max(np.abs(contributions - variance_budgets)) <= 1e-7:
                return weights

    marginal = covariance @ weights
    variance = float(weights @ marginal)
    contributions = weights * marginal / variance
    if np.max(np.abs(contributions - variance_budgets)) > 1e-5:
        raise ValueError("ERC solve did not converge")
    return weights


def _scale_targets(
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    multipliers: Mapping[SleeveName, float],
) -> dict[SleeveName, dict[str, float]]:
    scaled_targets: dict[SleeveName, dict[str, float]] = {}
    for name, targets in sleeve_targets.items():
        if name not in multipliers:
            continue
        scaled_targets[name] = _scale_sleeve_targets(
            targets,
            multiplier=multipliers[name],
        )
    return scaled_targets


def _scale_sleeve_targets(
    targets: Mapping[str, float],
    *,
    multiplier: float,
) -> dict[str, float]:
    scaled_targets: dict[str, float] = {}
    for figi, weight in targets.items():
        scaled = float(weight) * multiplier
        if abs(scaled) > _EPS:
            scaled_targets[figi] = scaled
    return scaled_targets
