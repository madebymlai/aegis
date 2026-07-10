"""The single seam that resolves how an instrument is marked (aegis-rd-tggo).

Every raw mark/fill resolution — catalog cold-fetch, catalog warm read,
distribution coverage, trader backtest wrangling, trader cache read, live
subscribe/unsubscribe/request — crosses one query-only
:class:`RawBarTypeResolver` and receives an :class:`InstrumentMarking` value
object.  The value object (not a single ``BarType``) is the seam's shape
because a quote-marked instrument needs *two* mark bars (BID + ASK) and a
derived mid; a single-``BarType`` return cannot express that.

The mark mode is **declared** where the instrument is named — one optional
token on the tradeable id (``UEQC.IBIS:QUOTE``, ``:MID``; absent = LAST),
parsed once at config load — plus static instrument facts for the defaults
(cash FX is bar-marked MID; IBKR serves no TRADES print for it).  A closed set
of three modes, not an open policy registry.

Architectural rule (ADR-0007 amendment, verified against the Nautilus docs):
``EXTERNAL`` L1 bars feed the simulated venue's order book, INTERNAL values
are strategy-only.  A quote-marked instrument therefore carries BID + ASK only
and *derives* its mid (``reference_price``); it must never also carry a
MID-EXTERNAL bar, which would feed the book as a zero-spread update.  That is
enforced structurally: :meth:`DeclaredMarkingResolver.resolve` is the only
builder of ``mark_bars`` and emits BID/ASK for QUOTE.

Consumers never branch on the mark mode: they subscribe/query ``mark_bars``,
mark at ``reference_price``, and project frames via ``ohlcv_frame``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pandas as pd

from aegis_data.bar_type import external_bar_type, mic_canonical_instrument_id
from aegis_data.ohlcv import bars_to_ohlcv

if TYPE_CHECKING:
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


class UnknownMarkTokenError(ValueError):
    """A declared mark-mode token outside the closed LAST/MID/QUOTE set."""

    def __init__(self, value: str, token: str) -> None:
        self.value = value
        self.token = token
        super().__init__(
            f"unknown mark-mode token {token!r} in {value!r}: expected one of "
            f"{', '.join(mode.value for mode in MarkMode)}"
        )


@dataclass(frozen=True)
class MarkDeclaration:
    """One tradeable as authored: its id plus the optional declared mark mode."""

    instrument_id: InstrumentId
    mode: MarkMode | None


def split_mark_token(value: str) -> tuple[str, MarkMode | None]:
    """Split ``SYMBOL.VENUE[:MODE]`` into the id spelling and the declared mode.

    The one home of the declaration grammar; config layers that keep ids as
    strings normalize through this, so the token can never be parsed two ways.
    An unknown token fails closed at config load, never at data time.
    """
    spelled, separator, token = value.partition(":")
    if not separator:
        return value, None
    try:
        return spelled, MarkMode(token)
    except ValueError:
        raise UnknownMarkTokenError(value, token) from None


def parse_mark_declaration(value: str) -> MarkDeclaration:
    """Parse ``SYMBOL.VENUE[:MODE]`` — the one token where the instrument is named.

    ``UEQC.IBIS:QUOTE`` declares a quote-marked leg; no token declares nothing
    (the resolver applies the LAST / cash-FX-MID defaults).
    """
    from nautilus_trader.model.identifiers import InstrumentId

    spelled, mode = split_mark_token(value)
    return MarkDeclaration(InstrumentId.from_str(spelled), mode)


class MarkBarMisalignmentError(ValueError):
    """The bars handed to a marking do not align with its ``mark_bars``."""


@dataclass(frozen=True)
class InstrumentMarking:
    """One instrument's resolved marking: which raw bars carry it, and how it marks.

    ``mark_bars`` aligns with the bars a consumer must load/subscribe: length 1
    for a bar-marked instrument, ``(BID, ASK)`` for a quote-marked one.  The
    mode stays a secret of this object — consumers call :meth:`reference_price`
    and :meth:`ohlcv_frame` instead of branching.
    """

    instrument_id: InstrumentId
    mode: MarkMode
    mark_bars: tuple[BarType, ...]

    def reference_price(self, latest: Sequence[Bar]) -> Price:
        """The mark price from *latest*, one bar per ``mark_bars`` entry in order.

        Bar-marked -> the single bar's close.  Quote-marked -> ``(bid + ask) / 2``
        of the BID/ASK closes — the single home of the mid formula, shared by
        every marking path (sim-book mark, recorder, financing, live) so they
        cannot silently diverge.
        """
        if len(latest) != len(self.mark_bars):
            raise MarkBarMisalignmentError(
                f"{self.instrument_id.value} marking expects "
                f"{len(self.mark_bars)} latest bar(s), got {len(latest)}"
            )
        if self.mode is MarkMode.QUOTE:
            return _mid_price(latest[0], latest[1])
        return latest[0].close

    def ohlcv_frame(self, bars_by_type: Mapping[BarType, Sequence[Bar]]) -> pd.DataFrame:
        """The corpus OHLCV frame for this marking from its stored mark bars.

        Bar-marked -> the single bar series' own OHLCV.  Quote-marked -> the
        *derived* mid frame, elementwise ``(bid + ask) / 2`` on days quoted on
        both sides — a strategy-side value; no MID bar is stored (ADR-0007).
        """
        if self.mode is MarkMode.QUOTE:
            bid = bars_to_ohlcv(bars_by_type[self.mark_bars[0]])
            ask = bars_to_ohlcv(bars_by_type[self.mark_bars[1]])
            index = bid.index.intersection(ask.index)
            return (bid.loc[index] + ask.loc[index]) / 2.0
        return bars_to_ohlcv(bars_by_type[self.mark_bars[0]])

    def quote_ohlcv_frames(
        self, bars_by_type: Mapping[BarType, Sequence[Bar]]
    ) -> tuple[pd.DataFrame, pd.DataFrame] | None:
        """The ``(bid, ask)`` OHLCV frames when quote-marked, ``None`` otherwise.

        The feed for the research-side fill projection (quote-driven fills):
        a bar-marked instrument simply has no sided quote, so callers need no
        mode branch.  Live never calls this — the fill projection is derived,
        research-only, and never serialized.
        """
        if self.mode is not MarkMode.QUOTE:
            return None
        return (
            bars_to_ohlcv(bars_by_type[self.mark_bars[0]]),
            bars_to_ohlcv(bars_by_type[self.mark_bars[1]]),
        )


def _mid_price(bid: Bar, ask: Bar) -> Price:
    from nautilus_trader.model.objects import Price

    # One extra decimal so the exact half-tick mid stays representable.
    precision = max(bid.close.precision, ask.close.precision) + 1
    return Price((bid.close.as_double() + ask.close.as_double()) / 2.0, precision)


@runtime_checkable
class RawBarTypeResolver(Protocol):
    """The one query-only seam from an instrument to its raw marking.

    Injected wherever a raw ``BarType`` used to be constructed inline, so a
    different marking policy (declared marks, bundle-backed live marks) plugs
    in behind the same call sites without reshaping them.
    """

    def resolve(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        ...


@runtime_checkable
class InstrumentFacts(Protocol):
    """Static instrument facts the mark-mode defaults read — never live market
    state, never a probe.  The highest test seam: fake facts resolve the whole
    marking with no broker and no catalog."""

    def is_cash_fx(self, instrument_id: InstrumentId) -> bool:
        """Whether the id names a cash FX pair (IBKR serves it MIDPOINT-only)."""
        ...


@dataclass(frozen=True)
class SymbolShapeFacts:
    """Cash FX recognised by its ``BASE/QUOTE`` symbol shape (ADR-0007).

    The one signal available before the instrument definition is resolved: on a
    cold fill the definition is seeded only *after* the bars are fetched.
    """

    def is_cash_fx(self, instrument_id: InstrumentId) -> bool:
        return "/" in instrument_id.symbol.value


@dataclass(frozen=True)
class DeclaredMarkingResolver:
    """Declaration + static facts -> :class:`InstrumentMarking` (aegis-rd-tggo.2).

    An explicitly declared mode wins; absent, a cash-FX id defaults to
    bar-marked MID (the IDEALPRO venue rule) and everything else to LAST.
    Stateless and query-only; with no declarations it reproduces the corpus
    rule byte-identically.  Declarations are keyed by the canonical corpus id,
    so the raw-IB-exchange and MIC spellings name one instrument.
    """

    declared: Mapping[InstrumentId, MarkMode] = field(default_factory=dict)
    facts: InstrumentFacts = SymbolShapeFacts()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "declared",
            {
                mic_canonical_instrument_id(instrument_id): mode
                for instrument_id, mode in self.declared.items()
            },
        )

    def resolve(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        corpus_id = mic_canonical_instrument_id(instrument_id)
        mode = self._mode(corpus_id)
        return InstrumentMarking(
            instrument_id=corpus_id,
            mode=mode,
            mark_bars=_mark_bars(corpus_id, timeframe, mode),
        )

    def _mode(self, corpus_id: InstrumentId) -> MarkMode:
        declared = self.declared.get(corpus_id)
        if declared is not None:
            return declared
        if self.facts.is_cash_fx(corpus_id):
            return MarkMode.MID
        return MarkMode.LAST


def _mark_bars(
    corpus_id: InstrumentId, timeframe: str, mode: MarkMode
) -> tuple[BarType, ...]:
    # The single builder of mark_bars: QUOTE emits BID + ASK and can never emit
    # a MID-EXTERNAL bar (the ADR-0007 EXTERNAL-drives-book constraint).
    if mode is MarkMode.QUOTE:
        return (
            external_bar_type(corpus_id, timeframe, "BID"),
            external_bar_type(corpus_id, timeframe, "ASK"),
        )
    return (external_bar_type(corpus_id, timeframe, mode.value),)


__all__ = [
    "DeclaredMarkingResolver",
    "InstrumentFacts",
    "InstrumentMarking",
    "MarkBarMisalignmentError",
    "MarkDeclaration",
    "MarkMode",
    "RawBarTypeResolver",
    "SymbolShapeFacts",
    "UnknownMarkTokenError",
    "parse_mark_declaration",
    "split_mark_token",
]
