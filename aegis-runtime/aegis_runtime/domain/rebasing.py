"""Re-basing a recorded value across a continuous-future roll (aegis-rd-iwx).

Owns the back-adjustment ALGEBRA in one place — additive for spread modes, multiplicative for ratio
modes — mirroring Nautilus's own cumulative-offset formulas (``docs/concepts/continuous_futures.md``):
spread adds a ``post - pre`` offset, ratio multiplies by a ``post / pre`` factor.

A caller that carries co-moving absolute state across a roll — the live
``ContinuousContractModel`` re-materializes the series while the ``SleeveLedger`` still
holds closes recorded in the old basis — stays **mode-blind**:
it holds a :class:`Rebasing` and calls :meth:`~Rebasing.apply`, never naming spread or ratio.  The
:class:`~aegis_data.continuous_future.ContinuousFuture` builds the right :class:`Rebasing` for a roll from
its own adjustment mode (:meth:`~aegis_data.continuous_future.ContinuousFuture.rebasing_for_roll`), so the
mode is chosen in exactly one place.

The aegis-rd-r8b.3 prototype verified empirically that under ratio the carry MUST be multiplicative — an
additive carry is wrong on every roll-spanning return — so this module makes that correctness a property
of the adapter, not a hand-edit at each call site.

Pure: no I/O, and a leaf (no dependency on the roll table).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AdjustmentMode(Protocol):
    """A declared continuous-future adjustment mode."""

    @property
    def is_ratio(self) -> bool:
        """Whether the mode re-bases values multiplicatively."""
        ...


@dataclass(frozen=True)
class RebasingParameters:
    """The distinct quantities required by additive and multiplicative modes."""

    additive_delta: float
    multiplicative_factor: float


class Rebasing(Protocol):
    """Carry one recorded price from the pre-roll basis into the post-roll basis."""

    def apply(self, value: float) -> float:
        """Return ``value`` re-based into the post-roll basis."""
        ...


@dataclass(frozen=True)
class _Spread:
    """Additive (Panama) re-basing — ``value + delta`` (spread mode: ``delta = post - pre``)."""

    delta: float

    def apply(self, value: float) -> float:
        return value + self.delta


@dataclass(frozen=True)
class _Ratio:
    """Multiplicative re-basing — ``value * factor`` (ratio mode: ``factor = post / pre``)."""

    factor: float

    def apply(self, value: float) -> float:
        return value * self.factor


@dataclass(frozen=True)
class _Identity:
    """No re-basing — the pre-first-roll state, or a seam that carries no shift."""

    def apply(self, value: float) -> float:
        return value


IDENTITY: Rebasing = _Identity()


def spread_rebasing(delta: float) -> Rebasing:
    """An additive re-basing by ``delta``."""
    return _Spread(delta)


def ratio_rebasing(factor: float) -> Rebasing:
    """A multiplicative re-basing by ``factor``."""
    return _Ratio(factor)


def rebasing_for_adjustment(
    mode: AdjustmentMode,
    parameters: RebasingParameters,
) -> Rebasing:
    """Build the re-basing whose semantics are declared by ``mode``."""
    if mode.is_ratio:
        return ratio_rebasing(parameters.multiplicative_factor)
    return spread_rebasing(parameters.additive_delta)


__all__ = [
    "IDENTITY",
    "AdjustmentMode",
    "Rebasing",
    "RebasingParameters",
    "ratio_rebasing",
    "rebasing_for_adjustment",
    "spread_rebasing",
]
