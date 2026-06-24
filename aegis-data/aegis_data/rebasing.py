"""Re-basing a recorded value across a continuous-future roll (aegis-rd-iwx).

Owns the back-adjustment ALGEBRA in one place — additive for spread modes, multiplicative for ratio
modes — mirroring Nautilus's own cumulative-offset formulas (``docs/concepts/continuous_futures.md``):

    BACKWARD_SPREAD: sum of (post_i - pre_i)      -> additive offset on the fixed-point PriceRaw
    BACKWARD_RATIO:  product of (post_i / pre_i)  -> multiplicative factor (requires positive prices)

A caller that carries co-moving absolute state across a roll — the live ``ContinuousFeed`` re-materializes
the series while the ``SleeveLedger`` still holds closes recorded in the old basis — stays **mode-blind**:
it holds a :class:`Rebasing` and calls :meth:`~Rebasing.apply`, never naming spread or ratio.  The
adjustment mode is read in exactly one place (:data:`~aegis_data.continuous_future.DEFAULT_ADJUSTMENT_MODE`),
so flipping that one constant switches both the Nautilus series arithmetic and this re-basing together.

The aegis-rd-r8b.3 prototype verified empirically that under ratio the carry MUST be multiplicative — an
additive carry is wrong on every roll-spanning return — so this module makes that correctness follow from
the mode rather than from a hand-edit at each call site.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE


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
    """No re-basing — the pre-first-roll state, or a seam with no overlap to read the shift from."""

    def apply(self, value: float) -> float:
        return value


IDENTITY: Rebasing = _Identity()


def spread_rebasing(delta: float) -> Rebasing:
    """An additive re-basing by ``delta``."""
    return _Spread(delta)


def ratio_rebasing(factor: float) -> Rebasing:
    """A multiplicative re-basing by ``factor``."""
    return _Ratio(factor)


def rebasing_between(
    old: pd.DataFrame,
    new: pd.DataFrame,
    *,
    mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE,
) -> Rebasing:
    """The re-basing carrying a pre-roll close from ``old`` into ``new`` after one roll: additive
    ``new - old`` for a spread mode, multiplicative ``new / old`` for a ratio mode (the per-seam term
    of Nautilus's cumulative offset).

    Read off the **most-recent** overlapping close — the current front's own segment, which is the
    unadjusted anchor of the old basis, so the read is the clean seam shift: exact for spread, and a
    single price-rounding for ratio (reading deep history instead would compound the per-bar rounding
    of both scaled materializations).  No overlap (or a non-positive anchor under ratio) is a no-op.
    """
    common = old.index.intersection(new.index)
    if len(common) == 0:
        return IDENTITY
    anchor = common[-1]
    old_close = float(old.loc[anchor, "Close"])
    new_close = float(new.loc[anchor, "Close"])
    if mode.is_ratio:
        return ratio_rebasing(new_close / old_close) if old_close > 0 else IDENTITY
    return spread_rebasing(new_close - old_close)


__all__ = ["IDENTITY", "Rebasing", "ratio_rebasing", "rebasing_between", "spread_rebasing"]
