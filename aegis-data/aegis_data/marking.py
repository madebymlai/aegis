"""The single seam that resolves how an instrument is marked (aegis-rd-tggo).

Every raw mark/fill resolution — catalog cold-fetch, catalog warm read,
distribution coverage, trader backtest wrangling, trader cache read, live
subscribe/unsubscribe/request — crosses one query-only
:class:`RawBarTypeResolver` and receives an :class:`InstrumentMarking` value
object.  The value object (not a single ``BarType``) is the seam's shape
because a quote-marked instrument needs *two* mark bars (BID + ASK) and a
derived mid; a single-``BarType`` return cannot express that.

Consumers never branch on the mark mode: they subscribe/query ``mark_bars``
and mark at ``reference_price``.  The one adapter today,
:class:`PreferLastResolver`, reproduces the corpus rule byte-identically
(LAST for tradeables, MID for cash FX — ADR-0007) as a single-bar marking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from nautilus_trader.model.enums import PriceType

from aegis_data.bar_type import raw_bar_type

if TYPE_CHECKING:
    from collections.abc import Sequence

    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.objects import Price


@unique
class MarkMode(Enum):
    """How an instrument's mark price is sourced (a closed set, ADR-0007).

    ``LAST``/``MID`` are bar-marked: one vendor OHLCV bar, marked at its close.
    ``QUOTE`` is quote-marked: BID + ASK bars, marked at their derived mid.
    """

    LAST = "LAST"
    MID = "MID"
    QUOTE = "QUOTE"


class MarkBarMisalignmentError(ValueError):
    """The latest bars handed to ``reference_price`` do not align with ``mark_bars``."""


@dataclass(frozen=True)
class InstrumentMarking:
    """One instrument's resolved marking: which raw bars carry it, and how it marks.

    ``mark_bars`` aligns with the bars a consumer must load/subscribe: length 1
    for a bar-marked instrument, ``(BID, ASK)`` for a quote-marked one.  The
    mode stays a secret of this object — consumers call :meth:`reference_price`
    instead of branching.
    """

    instrument_id: InstrumentId
    mode: MarkMode
    mark_bars: tuple[BarType, ...]

    def reference_price(self, latest: Sequence[Bar]) -> Price:
        """The mark price from *latest*, one bar per ``mark_bars`` entry in order.

        Bar-marked -> the single bar's close.  Quote-marked -> ``(bid + ask) / 2``
        of the BID/ASK closes — the single home of the mid formula, shared by
        every marking path so they cannot silently diverge.
        """
        if len(latest) != len(self.mark_bars):
            raise MarkBarMisalignmentError(
                f"{self.instrument_id.value} marking expects "
                f"{len(self.mark_bars)} latest bar(s), got {len(latest)}"
            )
        if self.mode is MarkMode.QUOTE:
            return _mid_price(latest[0], latest[1])
        return latest[0].close


def _mid_price(bid: Bar, ask: Bar) -> Price:
    from nautilus_trader.model.objects import Price

    # One extra decimal so the exact half-tick mid stays representable.
    precision = max(bid.close.precision, ask.close.precision) + 1
    return Price(
        (bid.close.as_double() + ask.close.as_double()) / 2.0, precision
    )


@runtime_checkable
class RawBarTypeResolver(Protocol):
    """The one query-only seam from an instrument to its raw marking.

    Injected wherever a raw ``BarType`` used to be constructed inline, so a
    different marking policy (declared marks, bundle-backed live marks) plugs
    in behind the same call sites without reshaping them.
    """

    def resolve(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        ...


@dataclass(frozen=True)
class PreferLastResolver:
    """Today's corpus rule as a resolver: LAST tradeables, MID cash FX (ADR-0007).

    A pure wrapper over :func:`aegis_data.bar_type.raw_bar_type` — same venue
    canonicalization, same price type, one mark bar, reference price = close —
    so threading the seam changes no behavior.
    """

    def resolve(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        bar_type = raw_bar_type(instrument_id, timeframe)
        mode = (
            MarkMode.MID
            if bar_type.spec.price_type == PriceType.MID
            else MarkMode.LAST
        )
        return InstrumentMarking(
            instrument_id=bar_type.instrument_id,
            mode=mode,
            mark_bars=(bar_type,),
        )


__all__ = [
    "InstrumentMarking",
    "MarkBarMisalignmentError",
    "MarkMode",
    "PreferLastResolver",
    "RawBarTypeResolver",
]
