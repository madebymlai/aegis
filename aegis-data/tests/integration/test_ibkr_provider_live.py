"""Live IBKR provider check — operator-run, against a real IB Gateway.

IBKR is a true-external dependency: these tests connect to a running gateway, so
they are skipped unless ``ibapi`` is installed *and* ``AEGIS_IBKR_GATEWAY_PORT``
is set to the gateway's port.  The adapter's own logic (param translation, asyncio
hiding) is covered without IBKR in ``tests/test_ibkr_provider.py``; these pin the
real contracts a fake cannot model — that the client returns ``EXTERNAL`` daily
bars, that ``request_instruments`` round-trips the native identity, and that the
full lazy fill persists real bars + the definition and then reads back warm.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    CatalogBackedDataPort,
    RawBarRequest,
    parquet_data_catalog,
)
from aegis_data.ibkr_provider import IbkrHistoricalProvider, seed_instrument_definitions

pytest.importorskip("ibapi")

_GATEWAY_PORT = os.environ.get("AEGIS_IBKR_GATEWAY_PORT")
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_START = pd.Timestamp("2024-01-02", tz="UTC")
_END = pd.Timestamp("2024-02-01", tz="UTC")

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def _provider(client_id: int) -> IbkrHistoricalProvider:
    # DELAYED_FROZEN so the checks run without a real-time data subscription;
    # they validate the read path + identity + persistence, not live streaming.
    return IbkrHistoricalProvider(
        port=int(_GATEWAY_PORT),  # type: ignore[arg-type]
        client_id=client_id,
        market_data_type="DELAYED_FROZEN",
    )


def test_request_bars_returns_external_daily_bars_from_ibkr() -> None:
    bars = _provider(7).request_bars(raw_bar_type(_AAPL, "1D"), start=_START, end=_END)

    assert bars
    assert all(bar.bar_type == raw_bar_type(_AAPL, "1D") for bar in bars)


def test_request_instruments_round_trips_native_identity() -> None:
    """The IB-simplified symbology returns a definition whose id is the native
    InstrumentId we asked for — the invariant AC6's catalog lookup relies on."""
    instruments = _provider(8).request_instruments((_AAPL,))

    assert any(instrument.id == _AAPL for instrument in instruments)


def test_lazy_fill_backfills_persists_and_then_reads_warm(tmp_path) -> None:
    """The production composition end to end against real IBKR: a miss fills bars
    AND seeds the definition; a provider-less re-read then serves from the catalog
    (warm, no IBKR), and the instrument definition is present (AC1/AC3/AC6)."""
    catalog_path = tmp_path / "catalog"
    provider = _provider(9)
    catalog = parquet_data_catalog(catalog_path)
    port = CatalogBackedDataPort(
        catalog,
        provider=provider,
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )
    request = RawBarRequest(instrument_ids=(_AAPL,), start="2024-01-02", end="2024-02-01")

    filled = port.load_raw_bars(request)
    assert not filled[_AAPL].empty
    assert (filled[_AAPL]["Close"] > 0).all()

    # Provider-less read: must serve entirely from the catalog (no IBKR contact).
    warm = CatalogBackedDataPort(parquet_data_catalog(catalog_path)).load_raw_bars(request)
    assert warm[_AAPL]["Close"].tolist() == filled[_AAPL]["Close"].tolist()

    # AC6: the served instrument's definition was persisted as a Step-1 write.
    definitions = parquet_data_catalog(catalog_path).instruments(
        instrument_ids=[_AAPL.value]
    )
    assert any(instrument.id == _AAPL for instrument in definitions)
