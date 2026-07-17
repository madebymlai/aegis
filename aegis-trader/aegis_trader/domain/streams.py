"""Market-data stream identity — the Book's per-stream data plan vocabulary.

A stream is one instrument consumed at one timeframe: the pure-domain mirror
of a Nautilus ``BarType`` subscription (aegis-rd-9qkr).  Book assembly derives
each Sleeve's required streams from its Execution Bundle contract and exposes
the deduplicated Book union, so startup and backtest consume one deterministic
plan instead of reconstructing a global request.

Continuous-future roots are not streams here: their dated front legs load
dynamically through the Roll Desk, which owns their subscription lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.types import SleeveName


@dataclass(frozen=True)
class MarketStream:
    """One market-data stream: an instrument consumed at a timeframe."""

    instrument_id: InstrumentId
    timeframe: str


@dataclass(frozen=True)
class StreamRequirement:
    """One deduplicated Book stream, its consumers, and its history depth.

    ``history_bars`` is the deepest consuming Sleeve's ``lookback_bars + 1`` —
    the bar count that Sleeve's compute needs, counted in this stream's own
    bar width.  ``consumers`` preserves the association from the deduplicated
    stream back to every Sleeve that reads it, in Sleeve-name order.
    """

    stream: MarketStream
    history_bars: int
    consumers: tuple[SleeveName, ...]


def stream_sort_key(stream: MarketStream) -> tuple[str, str]:
    """The one deterministic stream ordering: instrument value, then timeframe."""
    return (stream.instrument_id.value, stream.timeframe)


__all__ = [
    "MarketStream",
    "StreamRequirement",
    "stream_sort_key",
]
