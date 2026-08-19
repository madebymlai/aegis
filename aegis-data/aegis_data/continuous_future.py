"""The continuous-futures roll-transition table (Path A).

Aegis owns the *table*; Nautilus's ``DataEngine`` owns the *arithmetic*.  This turns
a dated-leg :class:`~aegis_data.chain.ContractChain` into the explicit roll
transitions Nautilus materialises a back-adjusted continuous series from.

Pure: no I/O, no Nautilus engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import continuous_bar_type
from aegis_data.chain import ContractChain
from aegis_runtime.domain.rebasing import IDENTITY, Rebasing, ratio_rebasing, spread_rebasing

# Ratio (proportional): each prior segment is scaled by the cumulative post/pre factor, so the
# adjusted series preserves percentage returns exactly — what the returns-based research metrics
# (Sharpe/vol from value.pct_change) consume, and what keeps research↔live in the percentage frame.
# Byte-exact at every trading precision (float drift only beyond 8dp, prototype NOTES.md V4); the live
# SleeveLedger re-bases multiplicatively in lock-step via the runtime domain's re-basing algebra. This is the mode research
# SELECTS for a new Run (aegis-rd-iwx) and records as Run evidence (root ADR-0009); it is not a silent
# fallback anywhere on the shared research/live path — live materialises under the locked bundle
# contract's recorded mode, and BACKWARD_SPREAD is a first-class choice for integer-exact additive offsets.
DEFAULT_ADJUSTMENT_MODE = ContinuousFutureAdjustmentType.BACKWARD_RATIO


@dataclass(frozen=True)
class RollTransition:
    """One roll seam of a continuous future: the leg rolling off (``pre``) and the leg
    rolling on (``post``) at ``transition_time_ns`` (bars at/after it are the post
    leg's), with each leg's Close on the roll day — the price gap the adjustment
    neutralises."""

    transition_time_ns: int
    pre_instrument_id: InstrumentId
    post_instrument_id: InstrumentId
    pre_price: float
    post_price: float

    def as_param(self) -> dict[str, object]:
        """The Nautilus ``continuous_future_transitions`` row — prices as strings, the
        documented shape (the fixed-point ``PriceRaw`` is precision-independent, so a
        string carries the value losslessly into the spread offset)."""
        return {
            "transition_time_ns": self.transition_time_ns,
            "pre_instrument_id": self.pre_instrument_id.value,
            "post_instrument_id": self.post_instrument_id.value,
            "pre_price": str(self.pre_price),
            "post_price": str(self.post_price),
        }


@dataclass(frozen=True)
class ContinuousFuture:
    """A continuous future ready to hand to Nautilus: the target (internally-aggregated)
    ``BarType`` and the roll transitions.

    The target root (``ES.XCME``) is a synthetic continuous root, not a real contract;
    each segment's source is a real leg named in ``transitions``.
    """

    target_bar_type: BarType
    transitions: tuple[RollTransition, ...]
    adjustment_mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE

    @property
    def instrument_id(self) -> InstrumentId:
        """The synthetic continuous-root id (``ES.XCME``) the materialized series is keyed by."""
        return self.target_bar_type.instrument_id

    def request_params(self) -> dict[str, object]:
        """The ``params`` for ``request_bars`` / ``subscribe_bars`` of this future."""
        return {
            "continuous_future_transitions": [t.as_param() for t in self.transitions],
            "continuous_future_adjustment_mode": self.adjustment_mode,
        }

    def rebasing_for_roll(self, rolled_from: InstrumentId, rolled_to: InstrumentId) -> Rebasing:
        """The exact re-basing carrying ``rolled_from``'s basis onto ``rolled_to``'s across the seam(s)
        between them — additive under a spread :attr:`adjustment_mode`, multiplicative under a ratio one.

        Read from the seam transition leg closes (the same prices Nautilus's engine uses), so the carry
        is byte-exact — unlike inferring the shift by diffing two rounded materializations.  A chain that
        does not connect the two legs carries no shift (a no-op).
        """
        seam = _seam_between(self.transitions, rolled_from, rolled_to)
        if not seam:
            return IDENTITY
        return _ratio_factor(seam) if self.adjustment_mode.is_ratio else _spread_delta(seam)


def continuous_future(
    chain: ContractChain,
    root_id: InstrumentId,
    *,
    timeframe: str = "1D",
    adjustment_mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE,
) -> ContinuousFuture:
    """Assemble the :class:`ContinuousFuture` keyed by the resolved continuous ``root_id``.

    Identity is resolved once, upstream, by
    :meth:`~aegis_data.catalog.CatalogBackedDataPort.resolve_continuous` (the sole venue-resolution
    site); this assembler receives the synthetic ``{root}.{venue}`` id (e.g. ``ES.XCME``) and
    never re-derives it from the chain.  ``adjustment_mode`` is an explicit fact on the
    shared research/live path (root ADR-0009): research passes the mode it records as Run
    evidence, live passes the locked bundle contract's mode, and the resulting
    :class:`ContinuousFuture` derives the matching roll carry from it.
    """
    return ContinuousFuture(
        target_bar_type=continuous_bar_type(root_id, timeframe),
        transitions=roll_transitions(chain),
        adjustment_mode=adjustment_mode,
    )


def roll_transitions(chain: ContractChain) -> tuple[RollTransition, ...]:
    """Derive the roll-transition table from a dated-leg chain — one per seam.

    The chain overlaps adjacent legs on the roll day, so both seam closes are present.
    """
    return tuple(
        RollTransition(
            transition_time_ns=_midnight_ns(roll_date),
            pre_instrument_id=InstrumentId.from_str(chain.symbols[seam]),
            post_instrument_id=InstrumentId.from_str(chain.symbols[seam + 1]),
            pre_price=_seam_close(chain.frames[seam], roll_date),
            post_price=_seam_close(chain.frames[seam + 1], roll_date),
        )
        for seam, roll_date in enumerate(chain.roll_dates)
    )


def _seam_close(frame: pd.DataFrame, roll_date: pd.Timestamp) -> float:
    return float(frame.loc[roll_date, "Close"])


def _midnight_ns(roll_date: pd.Timestamp) -> int:
    """The roll day's midnight UTC as integer ns — the segment boundary.  Daily bars
    sit at/after it on the roll day (post leg) and strictly before it the prior day
    (pre leg), so the seam is a clean day boundary."""
    return pd.Timestamp(roll_date).normalize().tz_localize("UTC").value


def _seam_between(
    transitions: Sequence[RollTransition], rolled_from: InstrumentId, rolled_to: InstrumentId
) -> list[RollTransition]:
    """The contiguous transition(s) carrying ``rolled_from``'s basis onto ``rolled_to``'s (empty if the
    chain does not connect them)."""
    seam: list[RollTransition] = []
    collecting = False
    for transition in transitions:
        if transition.pre_instrument_id == rolled_from:
            collecting = True
        if collecting:
            seam.append(transition)
            if transition.post_instrument_id == rolled_to:
                return seam
    return []


def _ratio_factor(seam: Sequence[RollTransition]) -> Rebasing:
    """The cumulative ``post / pre`` factor over ``seam`` — a no-op if a seam price is non-positive
    (Nautilus's ratio adjustment requires strictly positive prices)."""
    factor = 1.0
    for transition in seam:
        if transition.pre_price <= 0:
            return IDENTITY
        factor *= transition.post_price / transition.pre_price
    return ratio_rebasing(factor)


def _spread_delta(seam: Sequence[RollTransition]) -> Rebasing:
    """The cumulative ``post - pre`` offset over ``seam``."""
    delta = 0.0
    for transition in seam:
        delta += transition.post_price - transition.pre_price
    return spread_rebasing(delta)


__all__ = [
    "DEFAULT_ADJUSTMENT_MODE",
    "ContinuousFuture",
    "RollTransition",
    "continuous_future",
    "roll_transitions",
]
