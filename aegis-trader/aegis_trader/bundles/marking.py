"""Live-side recorded markings: a read-only view over the bundle (aegis-rd-tggo.3).

The exported bundle records each leg's mark mode; this module is the live
consumer.  It is deliberately shallow in surface and deep in guarantee: the
resolver can only *read* the recorded modes — there is no resolve-and-record
and no fill surface — so live structurally cannot re-derive a mark or see the
research fill projection.  The recorded marking is pinned in the locked
bundle: a later liquidity change never flips the mark under a running
deployment (re-declaration is an explicit config edit + re-export).

Fails closed: an id with no recorded marking raises rather than defaulting a
thin leg to a sparse LAST feed.  The one carve-out is a declared
continuous-future root and its dated legs, which are LAST by construction
(the continuous composite is built from LAST leg bars; ADR-0007 amendment).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import mic_canonical_instrument_id
from aegis_data.marking import InstrumentMarking, MarkMode, marking_for_mode

from aegis_trader.bundles.book import AssembledBook

# Futures delivery-month codes: the tail a dated leg's symbol carries after its
# root (e.g. ``ESM4`` = ``ES`` + June 2024).
_MONTH_CODES = frozenset("FGHJKMNQUVXZ")


class MissingRecordedMarkingError(ValueError):
    """A live consume found no recorded marking for an id (fail closed)."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        self.instrument_id = instrument_id
        super().__init__(
            f"the bundle records no mark mode for {instrument_id.value}; live "
            "never defaults a leg's mark — re-export the bundle so the "
            "declared marking travels with it (aegis-rd-tggo.3)"
        )


class ConflictingRecordedMarkingsError(ValueError):
    """Two sleeves record different mark modes for one instrument."""


@dataclass(frozen=True)
class RecordedMarkingResolver:
    """The bundle-recorded markings as the live ``RawBarTypeResolver``.

    A query-only view: ``resolve`` maps a recorded mode through the one shared
    marking builder, so live subscribes exactly the mark bars research
    validated (bar-marked -> the single LAST/MID EXTERNAL feed; quote-marked ->
    BID + ASK EXTERNAL with the mid derived via the shared reference_price).
    """

    recorded: Mapping[InstrumentId, MarkMode] = field(default_factory=dict)
    futures_roots: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recorded",
            {
                mic_canonical_instrument_id(instrument_id): mode
                for instrument_id, mode in self.recorded.items()
            },
        )

    def resolve(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        corpus_id = mic_canonical_instrument_id(instrument_id)
        mode = self.recorded.get(corpus_id)
        if mode is None and self._last_by_construction(corpus_id):
            mode = MarkMode.LAST
        if mode is None:
            raise MissingRecordedMarkingError(corpus_id)
        return marking_for_mode(corpus_id, timeframe, mode)

    @property
    def quote_marked_ids(self) -> frozenset[InstrumentId]:
        """The legs whose Portfolio valuation needs a published quote-mid mark."""
        return frozenset(
            instrument_id
            for instrument_id, mode in self.recorded.items()
            if mode is MarkMode.QUOTE
        )

    def _last_by_construction(self, corpus_id: InstrumentId) -> bool:
        symbol = corpus_id.symbol.value
        for root in self.futures_roots:
            if symbol == root:
                return True
            if symbol.startswith(root) and _is_dated_leg_tail(symbol[len(root):]):
                return True
        return False


def _is_dated_leg_tail(tail: str) -> bool:
    """Whether *tail* is a delivery code (``M4``, ``H25``) after a declared root."""
    return (
        2 <= len(tail) <= 3
        and tail[0] in _MONTH_CODES
        and tail[1:].isdigit()
    )


def union_recorded_markings(
    recorded_by_sleeve: Iterable[Mapping[InstrumentId, str]],
) -> dict[InstrumentId, MarkMode]:
    """Union the sleeves' recorded modes onto canonical ids; conflicts fail loud."""
    union: dict[InstrumentId, MarkMode] = {}
    for recorded in recorded_by_sleeve:
        for instrument_id, mode_name in recorded.items():
            corpus_id = mic_canonical_instrument_id(instrument_id)
            mode = MarkMode(mode_name)
            existing = union.get(corpus_id)
            if existing is not None and existing is not mode:
                raise ConflictingRecordedMarkingsError(
                    f"sleeves record conflicting mark modes for "
                    f"{corpus_id.value}: {existing.value} vs {mode.value}"
                )
            union[corpus_id] = mode
    return union


def recorded_marking_resolver(book: AssembledBook) -> RecordedMarkingResolver:
    """The book's one live marking view: the sleeves' recorded modes united."""
    return RecordedMarkingResolver(
        recorded=union_recorded_markings(
            bundle.contract.mark_modes for bundle in book.sleeves.values()
        ),
        futures_roots=frozenset(
            root
            for bundle in book.sleeves.values()
            for root in bundle.contract.futures
        ),
    )


__all__ = [
    "ConflictingRecordedMarkingsError",
    "MissingRecordedMarkingError",
    "RecordedMarkingResolver",
    "recorded_marking_resolver",
    "union_recorded_markings",
]
