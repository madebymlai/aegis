"""Pure diagonal risk-budget allocator.

The allocator owns the Trader-side risk-budget scaling seam: raw per-sleeve
weights from Execution Bundles in, risk-budget-scaled per-sleeve weights out.
This implementation covers the diagonal (zero-correlation) case from ADR-0004
and imports no Nautilus types.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from aegis_trader.domain.types import SleeveName

_EPS = 1e-12


@dataclass(frozen=True)
class Allocation:
    """Risk-budget-scaled sleeve targets and their scalar multipliers."""

    multipliers: Mapping[SleeveName, float]
    scaled_targets: Mapping[SleeveName, Mapping[str, float]]


def allocate_diagonal_vol_target(
    *,
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    risk_shares: Mapping[SleeveName, float],
    realized_vols: Mapping[SleeveName, float] | None,
    book_vol_target: float,
) -> Allocation:
    """Scale per-sleeve target weights to realize a diagonal risk budget.

    During warmup callers pass ``realized_vols=None`` and the allocator falls
    back to raw risk shares.  Once a vol estimate is supplied, every active
    sleeve with positive risk share must have a finite, positive volatility;
    missing or degenerate estimates fail closed rather than silently mis-sizing.
    """
    if book_vol_target <= 0 or not math.isfinite(book_vol_target):
        raise ValueError(f"book_vol_target must be positive, got {book_vol_target!r}")

    active = _active_sleeves(sleeve_targets, risk_shares)
    if not active:
        return Allocation(multipliers={}, scaled_targets={})
    if realized_vols is None:
        multipliers = {name: float(risk_shares[name]) for name in active}
        return Allocation(
            multipliers=multipliers,
            scaled_targets=_scale_targets(sleeve_targets, multipliers),
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
    return Allocation(
        multipliers=multipliers,
        scaled_targets=_scale_targets(sleeve_targets, multipliers),
    )


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


def _active_sleeves(
    sleeve_targets: Mapping[SleeveName, Mapping[str, float]],
    risk_shares: Mapping[SleeveName, float],
) -> tuple[SleeveName, ...]:
    active: list[SleeveName] = []
    for name, targets in sleeve_targets.items():
        share = float(risk_shares.get(name, 0.0))
        if share < -_EPS or not math.isfinite(share):
            raise ValueError(f"risk share for sleeve {name.value!r} must be finite and non-negative")
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
