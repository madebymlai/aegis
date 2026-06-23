"""The single IBKR adapter (ADR-0006/0008) — historic-fetch logic + live wiring.

IBKR itself is a true-external dependency, so the live socket cannot be unit
tested.  What *is* unit testable — and what these tests pin — is the adapter's
own logic: translating a ``BarType`` + window into the historic client's request
shape (naive UTC datetimes), hiding ``asyncio`` behind a synchronous port, and
connecting/closing around every call.  A fake session stands in for IBKR.  The
live client wiring (:func:`attach_live_clients`) needs ``ibapi`` and is covered
from the Trader's node tests (where ``ibapi`` is installed); here we pin only that
importing the adapter never pulls ``ibapi`` (the lazy boundary).
"""

from __future__ import annotations

import sys
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import NautilusDataProviderPort
from aegis_data.ibkr import IbkrHistoricalProvider, seed_instrument_definitions


class _FakeHistoricClient:
    def __init__(self, *, bars: list[Any], instruments: list[Any]) -> None:
        self._bars = bars
        self._instruments = instruments
        self.events: list[str] = []
        self.bar_calls: list[dict[str, Any]] = []
        self.instrument_calls: list[dict[str, Any]] = []

    async def connect(self) -> None:
        self.events.append("connect")

    async def aclose(self) -> None:
        self.events.append("aclose")

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
    # The historic client applies tz_name itself, so it must get NAIVE datetimes.
    assert call["start_date_time"] == datetime(2024, 1, 1)
    assert call["start_date_time"].tzinfo is None
    assert call["end_date_time"] == datetime(2024, 3, 1)


def test_request_bars_connects_and_closes_around_the_call() -> None:
    fake = _FakeHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
    )

    assert fake.events == ["connect", "aclose"]


def test_request_bars_closes_even_when_the_fetch_raises() -> None:
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

    assert fake.events == ["connect", "aclose"]


def test_unknown_market_data_type_fails_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown IB market_data_type"):
        IbkrHistoricalProvider(market_data_type="BOGUS")


def test_provider_satisfies_the_pure_fetch_port() -> None:
    port: NautilusDataProviderPort = IbkrHistoricalProvider(
        client_factory=lambda: _FakeHistoricClient(bars=[], instruments=[])
    )
    assert callable(port.request_bars)


def test_importing_the_adapter_does_not_import_ibapi() -> None:
    """The lazy-``ibapi`` boundary: importing the adapter (historic fetch *and*
    live wiring both live here) must not pull ``ibapi`` — every IBKR import is
    deferred to call time.  ``aegis-data`` runs without ``ibapi`` installed, so
    its mere absence from ``sys.modules`` after import is the invariant."""
    import aegis_data.ibkr  # noqa: F401 — import-for-effect

    assert "ibapi" not in sys.modules


# --------------------------------------------------------------------------- #
# live-client endpoint seam (no ibapi: pure connection -> endpoint kwargs)
# --------------------------------------------------------------------------- #


def test_endpoint_uses_explicit_host_port_when_no_dockerized_gateway() -> None:
    """The skeleton path: an explicit gateway endpoint, no dockerized variant."""
    from aegis_data.ibkr import _gateway_endpoint

    connection = SimpleNamespace(
        host="10.0.0.5", port=4002, client_id=9,
        account_id="DU1234567", dockerized_gateway=None,
    )

    assert _gateway_endpoint(connection) == {"ibg_host": "10.0.0.5", "ibg_port": 4002}


def test_endpoint_defers_to_dockerized_gateway_when_set() -> None:
    """The r8b.6 seam: a ``dockerized_gateway`` supplies its own endpoint, so the
    explicit host/port are omitted (the two are mutually exclusive)."""
    from aegis_data.ibkr import _gateway_endpoint

    gateway = object()
    connection = SimpleNamespace(
        host="10.0.0.5", port=4002, client_id=9,
        account_id="DU1234567", dockerized_gateway=gateway,
    )

    assert _gateway_endpoint(connection) == {"dockerized_gateway": gateway}


class _Instr:
    def __init__(self, instrument_id: InstrumentId) -> None:
        self.id = instrument_id


class _FakeCatalog:
    def __init__(self, present: list[_Instr] | None = None) -> None:
        self._present = present or []
        self.writes: list[list[Any]] = []

    def instruments(self, *, instrument_ids: list[str]) -> list[_Instr]:
        wanted = set(instrument_ids)
        return [
            instrument for instrument in self._present if instrument.id.value in wanted
        ]

    def write_data(self, data: list[Any]) -> None:
        self.writes.append(data)


def test_seed_writes_all_definitions_when_none_present() -> None:
    aapl = InstrumentId.from_str("AAPL.NASDAQ")
    vusa = InstrumentId.from_str("VUSA.XLON")
    fetched = [_Instr(aapl), _Instr(vusa)]
    fake = _FakeHistoricClient(bars=[], instruments=fetched)
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    catalog = _FakeCatalog()

    seed_instrument_definitions(catalog, provider, (aapl, vusa))

    assert fake.instrument_calls[0]["instrument_ids"] == ["AAPL.NASDAQ", "VUSA.XLON"]
    assert catalog.writes == [fetched]


def test_seed_fetches_only_the_missing_definitions() -> None:
    aapl = InstrumentId.from_str("AAPL.NASDAQ")
    vusa = InstrumentId.from_str("VUSA.XLON")
    fetched = [_Instr(vusa)]
    fake = _FakeHistoricClient(bars=[], instruments=fetched)
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    catalog = _FakeCatalog(present=[_Instr(aapl)])

    seed_instrument_definitions(catalog, provider, (aapl, vusa))

    assert fake.instrument_calls[0]["instrument_ids"] == ["VUSA.XLON"]
    assert catalog.writes == [fetched]


def test_seed_is_a_noop_and_never_connects_when_all_present() -> None:
    aapl = InstrumentId.from_str("AAPL.NASDAQ")
    fake = _FakeHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    catalog = _FakeCatalog(present=[_Instr(aapl)])

    seed_instrument_definitions(catalog, provider, (aapl,))

    assert fake.events == []
    assert fake.instrument_calls == []
    assert catalog.writes == []
