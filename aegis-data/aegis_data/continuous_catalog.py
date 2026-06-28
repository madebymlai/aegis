"""Catalog-driven continuous-future materialisation (Path A, request path).

The single entry point research's request path calls: given the catalog-backed port and
a bare root (e.g. ``"ES"``), build the dated-leg chain through the catalog seams
(:mod:`aegis_data.catalog_contracts`), turn it into the roll-transition table
(:mod:`aegis_data.continuous_future`), and drive Nautilus's in-process ``DataEngine``
(:mod:`aegis_data.continuous_materialize`) to materialise the adjusted continuous series
**on demand, never persisted** (r8b.2).

This is the catalog-facing composer; the building blocks it ties together (chain, roll
table, engine) stay provider-neutral and are tested in isolation.  The byte-exact spread
arithmetic is gated by ``test_continuous_golden``; here the catalog reads — the dated-leg
definitions, their native ``Bar``\\ s, the OHLCV the roll prices come from — are kept in
this package alongside the port that owns them, so callers receive ready OHLCV frames and
never learn the Nautilus query surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import FuturesContract

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest, bars_to_ohlcv
from aegis_data.catalog_contracts import (
    catalog_contract_calendar,
    catalog_contract_fetcher,
    catalog_volume_probe,
)
from aegis_data.chain import fetch_contract_chain
from aegis_data.continuous_future import ContinuousFuture, continuous_future
from aegis_data.continuous_materialize import materialize_continuous_bars
from aegis_data.roll import DatedContract


def continuous_ohlcv_frames(
    port: CatalogBackedDataPort,
    roots: Sequence[str],
    *,
    start: str,
    end: str,
    timeframe: str = "1D",
) -> dict[InstrumentId, pd.DataFrame]:
    """Adjusted continuous OHLCV for each bare ``root``, keyed by its synthetic root id.

    The id is ``{root}.{venue}`` (venue catalog-authoritative from the dated legs, e.g.
    ``ES`` over XCME legs → ``ES.XCME``).  Each frame is the engine's back-adjusted
    series over ``[start, end]`` (OHLCV columns, event-time-ordered index) — identical in
    shape to a raw-leg frame, so the caller merges it like any other instrument.
    """
    frames = (_continuous_frame(port, root, start=start, end=end, timeframe=timeframe) for root in roots)
    return {future.instrument_id: frame for future, frame in frames}


def continuous_instrument_ids(
    port: CatalogBackedDataPort,
    roots: Sequence[str],
    *,
    start: str,
    end: str,
) -> tuple[InstrumentId, ...]:
    """Resolve bare continuous-future roots to synthetic continuous InstrumentIds.

    The venue is catalog-authoritative from the dated legs. This is the cheap resolver
    for callers that need the live/research column id but not the materialised bars.
    """
    catalog = port.catalog
    return tuple(
        _continuous_instrument_id(root, _root_legs(catalog, root, start, end))
        for root in roots
    )


def continuous_frame_and_future(
    port: CatalogBackedDataPort,
    root: str,
    *,
    start: str,
    end: str,
    timeframe: str = "1D",
) -> tuple[ContinuousFuture, pd.DataFrame]:
    """The adjusted continuous OHLCV for one ``root`` **and** the :class:`ContinuousFuture` it was
    materialised from (its roll transitions + adjustment mode).

    The live feed needs the future so it can re-base co-moving state from the exact seam leg closes at
    a roll, rather than inferring the shift by diffing two rounded materialisations.  The frame is
    identical to the matching :func:`continuous_ohlcv_frames` entry.
    """
    return _continuous_frame(port, root, start=start, end=end, timeframe=timeframe)


def _continuous_frame(
    port: CatalogBackedDataPort,
    root: str,
    *,
    start: str,
    end: str,
    timeframe: str,
) -> tuple[ContinuousFuture, pd.DataFrame]:
    catalog = port.catalog
    legs = _root_legs(catalog, root, start, end)
    resolved_id = _continuous_instrument_id(root, legs)
    chain = fetch_contract_chain(
        root,
        pd.Timestamp(start).date(),
        pd.Timestamp(end).date(),
        list_contracts=lambda *_args: legs,
        fetch=catalog_contract_fetcher(port, timeframe=timeframe),
        bar_cadence=_bar_cadence(timeframe),
        probe_volume=catalog_volume_probe(port, timeframe=timeframe),
    )
    future = continuous_future(chain, root, timeframe=timeframe)
    if future.instrument_id != resolved_id:
        raise ValueError(
            f"continuous-future root {root!r} resolved to {resolved_id.value!r}, "
            f"but materialisation built {future.instrument_id.value!r}"
        )
    # Native ``Bar``\s (not the chain's float OHLCV) preserve the fixed-point ``PriceRaw``
    # the spread is integer-exact in, so research's series matches live's byte-for-byte.
    # The chain fetch already warmed these legs, so the port read is a warm hit; the leg
    # ``FuturesContract`` definitions are the catalog's to supply (the port is bars-only).
    leg_ids = tuple(InstrumentId.from_str(symbol) for symbol in chain.symbols)
    leg_bars = port.read_native_bars(RawBarRequest(leg_ids, start, end, timeframe))
    leg_instruments = catalog.instruments(
        instrument_type=FuturesContract, instrument_ids=list(chain.symbols)
    )
    bars = materialize_continuous_bars(
        future,
        leg_instruments=leg_instruments,
        leg_bars=leg_bars,
        start=pd.Timestamp(start, tz="UTC"),
        end=pd.Timestamp(end, tz="UTC"),
    )
    return future, bars_to_ohlcv(bars)


def _root_legs(catalog: object, root: str, start: str, end: str) -> Sequence[DatedContract]:
    """The root's dated legs — fail loud when the catalog has no cycle."""
    legs = catalog_contract_calendar(catalog)(root, pd.Timestamp(start).date(), pd.Timestamp(end).date())
    if not legs:
        raise ValueError(f"no dated legs in the catalog for continuous-future root {root!r}")
    return legs


def _continuous_instrument_id(root: str, legs: Sequence[DatedContract]) -> InstrumentId:
    """The synthetic root id, with venue validated from the dated legs."""
    venues = {InstrumentId.from_str(leg.symbol).venue for leg in legs}
    if len(venues) != 1:
        raise ValueError(
            f"continuous-future root {root!r} legs span multiple venues "
            f"{sorted(venue.value for venue in venues)}; expected one"
        )
    return InstrumentId(Symbol(root), next(iter(venues)))


def _bar_cadence(timeframe: str) -> timedelta:
    return pd.Timedelta(timeframe_to_ns(timeframe), unit="ns").to_pytimedelta()


__all__ = [
    "continuous_frame_and_future",
    "continuous_instrument_ids",
    "continuous_ohlcv_frames",
]
