"""The continuous-futures roll-transition table (Path A).

Aegis owns the *table*; Nautilus's ``DataEngine`` owns the *arithmetic*.  This turns
a dated-leg :class:`~aegis_data.chain.ContractChain` into the explicit roll
transitions Nautilus materialises a back-adjusted continuous series from.

Pure: no I/O, no Nautilus engine.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from aegis_data.bar_type import continuous_bar_type
from aegis_data.chain import ContractChain

# Ratio (proportional): each prior segment is scaled by the cumulative post/pre factor, so the
# adjusted series preserves percentage returns exactly — what the returns-based research metrics
# (Sharpe/vol from value.pct_change) consume, and what keeps research↔live in the percentage frame.
# Byte-exact at every trading precision (float drift only beyond 8dp, prototype NOTES.md V4); the live
# SleeveLedger re-bases multiplicatively in lock-step via aegis_data.rebasing.  This is the default mode
# Aegis ships (aegis-rd-iwx); BACKWARD_SPREAD stays reachable via the explicit adjustment_mode for any
# caller needing integer-exact additive offsets.
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

    def request_params(self) -> dict[str, object]:
        """The ``params`` for ``request_bars`` / ``subscribe_bars`` of this future."""
        return {
            "continuous_future_transitions": [t.as_param() for t in self.transitions],
            "continuous_future_adjustment_mode": self.adjustment_mode,
        }


def continuous_future(
    chain: ContractChain,
    root: str,
    *,
    timeframe: str = "1D",
    adjustment_mode: ContinuousFutureAdjustmentType = DEFAULT_ADJUSTMENT_MODE,
) -> ContinuousFuture:
    """Assemble the :class:`ContinuousFuture` for ``root`` from its dated-leg chain.

    The target root inherits the legs' venue (every leg of a root trades one venue), so
    the synthetic root id is ``{root}.{venue}`` (e.g. ``ES`` over ``XCME`` legs →
    ``ES.XCME``); ``root`` is supplied because it is not a derivable prefix of the leg
    symbols.  ``adjustment_mode`` defaults to the one switch (:data:`DEFAULT_ADJUSTMENT_MODE`)
    that also drives the live re-basing, so a caller never names spread or ratio.
    """
    root_id = InstrumentId(Symbol(root), _chain_venue(chain))
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


def _chain_venue(chain: ContractChain) -> Venue:
    return InstrumentId.from_str(chain.symbols[0]).venue


__all__ = [
    "DEFAULT_ADJUSTMENT_MODE",
    "ContinuousFuture",
    "RollTransition",
    "continuous_future",
    "roll_transitions",
]
