"""The concrete IBKR DataProvider port (ADR-0006/0008).

IBKR itself is a true-external dependency, so the live socket cannot be unit
tested.  What *is* unit testable — and what these tests pin — is the adapter's
own logic: translating a ``BarType`` + window into the historic client's request
shape, hiding ``asyncio`` behind a synchronous port, and connecting/disconnecting
around every call.  A fake async client stands in for IBKR.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import NautilusDataProviderPort
from aegis_data.ibkr_provider import IbkrHistoricalProvider, seed_instrument_definitions


class _FakeHistoricClient:
    def __init__(self, *, bars: list[Any], instruments: list[Any]) -> None:
        self._bars = bars
        self._instruments = instruments
        self.events: list[str] = []
        self.bar_calls: list[dict[str, Any]] = []
        self.instrument_calls: list[dict[str, Any]] = []

    async def connect(self) -> None:
        self.events.append("connect")

    async def disconnect(self) -> None:
        self.events.append("disconnect")

    async def request_bars(self, **kwargs: Any) -> list[Any]:
        self.bar_calls.append(kwargs)
        return self._bars

    async def request_instruments(self, **kwargs: Any) -> list[Any]:
        self.instrument_calls.append(kwargs)
        return self._instruments


def test_request_bars_maps_bar_type_and_window_then_returns_bars() -> None:
    sentinel_bars = [object(), object()]
    fake = _FakeHistoricClient(bars=sentinel_bars, instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-03-01", tz="UTC"),
    )

    assert list(out) == sentinel_bars
    call = fake.bar_calls[0]
    assert call["bar_specifications"] == ["1-DAY-LAST"]
    assert call["instrument_ids"] == ["AAPL.NASDAQ"]
    assert call["tz_name"] == "UTC"
    assert call["start_date_time"] == pd.Timestamp("2024-01-01", tz="UTC").to_pydatetime()
    assert call["end_date_time"] == pd.Timestamp("2024-03-01", tz="UTC").to_pydatetime()


def test_request_bars_connects_and_disconnects_around_the_call() -> None:
    fake = _FakeHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
    )

    assert fake.events == ["connect", "disconnect"]


def test_request_bars_disconnects_even_when_the_fetch_raises() -> None:
    class _Boom(_FakeHistoricClient):
        async def request_bars(self, **kwargs: Any) -> list[Any]:
            raise RuntimeError("ib down")

    fake = _Boom(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(RuntimeError, match="ib down"):
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )

    assert fake.events == ["connect", "disconnect"]


def test_unknown_market_data_type_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown IB market_data_type"):
        IbkrHistoricalProvider(market_data_type="BOGUS")


def test_provider_satisfies_the_pure_fetch_port() -> None:
    port: NautilusDataProviderPort = IbkrHistoricalProvider(
        client_factory=lambda: _FakeHistoricClient(bars=[], instruments=[])
    )
    assert callable(port.request_bars)


def test_seed_instrument_definitions_is_a_step1_write_through_the_catalog() -> None:
    instruments = [object(), object()]
    fake = _FakeHistoricClient(bars=[], instruments=instruments)
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    writes: list[list[Any]] = []

    class _Catalog:
        def write_data(self, data: list[Any]) -> None:
            writes.append(data)

    seed_instrument_definitions(
        _Catalog(),
        provider,
        (InstrumentId.from_str("AAPL.NASDAQ"), InstrumentId.from_str("VUSA.XLON")),
    )

    assert fake.instrument_calls[0]["instrument_ids"] == ["AAPL.NASDAQ", "VUSA.XLON"]
    assert writes == [instruments]
