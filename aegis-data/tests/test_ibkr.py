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

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogWindowRequest,
    GapFillProviderError,
    NautilusDataProviderPort,
    ServedBars,
)
from aegis_data.ibkr import (
    IbkrHistoricalProvider,
    IbkrRequestError,
    seed_instrument_definitions,
)
from aegis_data.ibkr.historical import _HistoricSession


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


class _SlowEmptyHistoricClient(_FakeHistoricClient):
    async def request_bars(self, **kwargs: Any) -> list[Any]:
        await asyncio.sleep(kwargs["timeout"])
        return []


class _VendorRequest:
    def __init__(self, future: asyncio.Future[list[Any]], req_id: int = 17) -> None:
        self.future = future
        self.req_id = req_id


class _FailureSwallowingNativeClient:
    async def _await_request(
        self,
        request: _VendorRequest,
        timeout: int,
        default_value: Any | None = None,
        suppress_timeout_warning: bool = False,
    ) -> Any:
        del timeout, suppress_timeout_warning
        try:
            return await request.future
        except ConnectionError:
            return default_value

    async def _stop_async(self) -> None:
        pass


class _ConnectionFailingVendorClient:
    def __init__(self) -> None:
        self._client = _FailureSwallowingNativeClient()

    async def connect(self) -> None:
        pass

    async def request_bars(self, **kwargs: Any) -> list[Any]:
        del kwargs
        future = asyncio.get_running_loop().create_future()
        future.set_exception(ConnectionError("IB Gateway connection lost"))
        return await self._client._await_request(
            _VendorRequest(future),
            timeout=120,
            default_value=[],
        )

    async def request_instruments(self, **kwargs: Any) -> list[Any]:
        del kwargs
        return []


class _EmptyVendorClient(_ConnectionFailingVendorClient):
    async def request_bars(self, **kwargs: Any) -> list[Any]:
        del kwargs
        future = asyncio.get_running_loop().create_future()
        future.set_result([])
        return await self._client._await_request(
            _VendorRequest(future),
            timeout=120,
            default_value=[],
        )


def test_request_bars_maps_bar_type_and_window_then_returns_bars() -> None:
    served = [_StampedBar("2024-01-02"), _StampedBar("2024-02-01")]
    fake = _FakeHistoricClient(bars=served, instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-03-01", tz="UTC"),
    )

    assert list(out.bars) == served
    # The oldest bar is one closure past the requested start, so history covers it:
    # coverage is served from the requested start (contiguous with any prior file).
    assert out.served_from == pd.Timestamp("2024-01-01", tz="UTC")
    assert len(fake.bar_calls) == 1
    call = fake.bar_calls[0]
    assert call["bar_specifications"] == ["1-DAY-LAST"]
    assert call["instrument_ids"] == ["AAPL.XNAS"]
    assert call["tz_name"] == "UTC"
    # One native request: a whole-window `duration` ending at the NAIVE end (the
    # historic client applies tz_name itself); no start_date_time backward walk.
    assert call["duration"] == "60 D"
    assert call["end_date_time"] == datetime(2024, 3, 1)
    assert call["end_date_time"].tzinfo is None
    assert "start_date_time" not in call


def test_request_bars_asks_one_native_duration_for_a_wide_window() -> None:
    """A window wider than a single IB request's limit is served by ONE native
    request whose `duration` spans the whole window; Nautilus segments it by
    duration internally, so the provider does not re-walk it in yearly chunks."""
    served = [_StampedBar("2016-06-02"), _StampedBar("2017-06-01")]
    fake = _FakeHistoricClient(bars=served, instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2016-06-01", tz="UTC"),
        end=pd.Timestamp("2018-01-01", tz="UTC"),
    )

    assert len(fake.bar_calls) == 1
    assert fake.bar_calls[0]["duration"] == "2 Y"
    assert fake.bar_calls[0]["end_date_time"] == datetime(2018, 1, 1)
    assert "start_date_time" not in fake.bar_calls[0]
    assert list(out.bars) == served
    assert out.served_from == pd.Timestamp("2016-06-01", tz="UTC")
    # One session serves the request — connect/close wrap it once.
    assert fake.events == ["connect", "aclose"]


class _StampedBar:
    def __init__(self, day: str) -> None:
        self.ts_event = pd.Timestamp(day, tz="UTC").value


def test_request_bars_claims_nothing_when_no_bars_are_returned() -> None:
    """An empty answer claims no coverage: ``served_from`` falls back to the window
    end, so the coverage gate sees the whole window as unserved (nothing to write)."""
    fake = _FakeHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-03-01", tz="UTC"),
    )

    assert list(out.bars) == []
    assert out.served_from == pd.Timestamp("2024-03-01", tz="UTC")


def test_request_bars_preempts_session_empty_fallback() -> None:
    """The request deadline fires before a slow session can fall back to ``[]``."""
    fake = _SlowEmptyHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(
        client_factory=lambda: fake,
        timeout=1,
        call_deadline=2,
    )
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )

    assert isinstance(excinfo.value.__cause__, TimeoutError)


def test_request_bars_preserves_vendor_connection_failure() -> None:
    vendor = _ConnectionFailingVendorClient()
    provider = IbkrHistoricalProvider(
        client_factory=lambda: _HistoricSession(vendor),
    )
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )

    completion_error = excinfo.value.__cause__
    assert isinstance(completion_error, RuntimeError)
    assert isinstance(completion_error.__cause__, ConnectionError)


def test_request_bars_preserves_genuine_empty_vendor_history() -> None:
    vendor = _EmptyVendorClient()
    provider = IbkrHistoricalProvider(
        client_factory=lambda: _HistoricSession(vendor),
    )
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    result = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
    )

    assert result == ServedBars((), pd.Timestamp("2024-02-01", tz="UTC"))


def test_historical_failure_scope_resets_before_unrelated_requests() -> None:
    vendor = _ConnectionFailingVendorClient()
    session = _HistoricSession(vendor)

    async def exercise_session() -> tuple[RuntimeError | None, list[Any]]:
        failure: RuntimeError | None = None
        try:
            await session.request_bars()
        except RuntimeError as exc:
            failure = exc

        future = asyncio.get_running_loop().create_future()
        future.set_exception(ConnectionError("unrelated request failed"))
        unrelated_result = await vendor._client._await_request(
            _VendorRequest(future, req_id=18),
            timeout=120,
            default_value=[],
        )
        return failure, unrelated_result

    failure, unrelated_result = asyncio.run(exercise_session())

    assert isinstance(failure, RuntimeError)
    assert unrelated_result == []


def test_historical_session_matches_installed_request_await_contract() -> None:
    """Guard the one intentional private upstream reach in the session adapter."""
    check = """
from inspect import Parameter, signature

from nautilus_trader.adapters.interactive_brokers.client.client import (
    InteractiveBrokersClient,
)
from aegis_data.ibkr.historical import _HistoricSession

vendor = signature(InteractiveBrokersClient._await_request).parameters
adapter = signature(_HistoricSession._await_request_preserving_failure).parameters
expected_names = (
    "self",
    "request",
    "timeout",
    "default_value",
    "suppress_timeout_warning",
)
assert tuple(vendor) == expected_names
assert vendor["self"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert vendor["request"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert vendor["timeout"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert vendor["default_value"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert vendor["suppress_timeout_warning"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert vendor["self"].default is Parameter.empty
assert vendor["request"].default is Parameter.empty
assert vendor["timeout"].default is Parameter.empty
assert vendor["default_value"].default is None
assert vendor["suppress_timeout_warning"].default is False
assert tuple(adapter) == expected_names
assert adapter["self"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert adapter["request"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert adapter["timeout"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert adapter["default_value"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert adapter["suppress_timeout_warning"].kind is Parameter.POSITIONAL_OR_KEYWORD
assert adapter["self"].default is Parameter.empty
assert adapter["request"].default is Parameter.empty
assert adapter["timeout"].default is Parameter.empty
assert adapter["default_value"].default is None
assert adapter["suppress_timeout_warning"].default is False
"""

    subprocess.run(
        [sys.executable, "-c", check],
        check=True,
        capture_output=True,
        text=True,
    )


def test_catalog_port_preserves_vendor_connection_failure(tmp_path: Path) -> None:
    vendor = _ConnectionFailingVendorClient()
    provider = IbkrHistoricalProvider(
        client_factory=lambda: _HistoricSession(vendor),
    )
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path), provider=provider)
    request = CatalogWindowRequest(
        instrument_ids=(InstrumentId.from_str("AAPL.NASDAQ"),),
        start="2024-01-01",
        end="2024-02-01",
    )

    with pytest.raises(GapFillProviderError) as excinfo:
        port.load_window(request)

    provider_error = excinfo.value.__cause__
    assert isinstance(provider_error, IbkrRequestError)
    completion_error = provider_error.__cause__
    assert isinstance(completion_error, RuntimeError)
    assert isinstance(completion_error.__cause__, ConnectionError)


def test_catalog_port_translates_request_deadline_to_provider_failure(
    tmp_path: Path,
) -> None:
    fake = _SlowEmptyHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(
        client_factory=lambda: fake,
        timeout=1,
        call_deadline=2,
    )
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path), provider=provider)
    request = CatalogWindowRequest(
        instrument_ids=(InstrumentId.from_str("AAPL.NASDAQ"),),
        start="2024-01-01",
        end="2024-02-01",
    )

    with pytest.raises(GapFillProviderError) as excinfo:
        port.load_window(request)

    assert isinstance(excinfo.value.__cause__, IbkrRequestError)
    assert isinstance(excinfo.value.__cause__.__cause__, TimeoutError)


def test_request_bars_serves_from_the_listing_when_history_clamps_short() -> None:
    """GH #75: IB clamps its answer at the instrument's earliest available data, so a
    single request reaching before the listing simply returns fewer bars — the
    provider never steps into empty pre-listing history.  The oldest returned bar IS
    where history begins: coverage is served from there (far past the requested
    start), and the pre-listing head stays unclaimed for the coverage gate."""
    listing_date = pd.Timestamp("2016-06-15", tz="UTC")
    served = [_StampedBar("2016-06-15"), _StampedBar("2017-03-01")]
    fake = _FakeHistoricClient(bars=served, instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("TLT.XNAS"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2013-01-01", tz="UTC"),
        end=pd.Timestamp("2018-01-01", tz="UTC"),
    )

    # One request; IB returned only from the listing.
    assert len(fake.bar_calls) == 1
    assert list(out.bars) == served
    # The gap from 2013 to the first bar is far wider than a market closure, so it
    # reads as IB clamping at the listing: coverage begins at that first bar, not the
    # requested 2013 start, leaving the pre-listing head for the coverage gate.
    assert out.served_from == listing_date


def test_request_bars_can_pass_expired_future_contracts() -> None:
    served = [_StampedBar("2026-03-02")]
    fake = _FakeHistoricClient(bars=served, instruments=[])
    provider = IbkrHistoricalProvider(
        include_expired_futures=True,
        client_factory=lambda: fake,
    )
    bar_type = raw_bar_type(InstrumentId.from_str("ESM6.XCME"), "1D")

    out = provider.request_bars(
        bar_type,
        start=pd.Timestamp("2026-03-01", tz="UTC"),
        end=pd.Timestamp("2026-06-23", tz="UTC"),
    )

    assert list(out.bars) == served
    call = fake.bar_calls[0]
    assert "instrument_ids" not in call
    contract = call["contracts"][0]
    assert contract.secType == "FUT"
    assert contract.exchange == "CME"
    assert contract.localSymbol == "ESM6"
    assert contract.includeExpired is True


def test_request_bars_keeps_non_futures_on_instrument_ids_when_expired_enabled() -> (
    None
):
    fake = _FakeHistoricClient(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(
        include_expired_futures=True,
        client_factory=lambda: fake,
    )
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.XNAS"), "1D")

    provider.request_bars(
        bar_type,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
    )

    call = fake.bar_calls[0]
    assert call["instrument_ids"] == ["AAPL.XNAS"]
    assert "contracts" not in call


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


def test_request_bars_wraps_a_fault_in_a_named_error_and_still_closes() -> None:
    """A fault during the fetch surfaces as one ``IbkrRequestError`` naming the
    bar type (not a bare error), with the original chained — and the session is
    still closed."""

    class _Boom(_FakeHistoricClient):
        async def request_bars(self, **kwargs: Any) -> list[Any]:
            raise RuntimeError("ib down")

    fake = _Boom(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )

    assert str(bar_type) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert str(excinfo.value.__cause__) == "ib down"
    assert fake.events == ["connect", "aclose"]


def test_request_bars_converts_a_dead_vendor_call_into_a_named_error() -> None:
    """The other face of #75: the vendor stack has unbounded awaits (a stuck
    qualification when an instrument cannot resolve to one asset, shared-request
    futures).  A session call that makes no progress past the deadline surfaces
    as an ``IbkrRequestError`` instead of hanging forever."""

    class _Stuck(_FakeHistoricClient):
        async def request_bars(self, **kwargs: Any) -> list[Any]:
            await asyncio.sleep(3600)
            return []

    fake = _Stuck(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake, call_deadline=0.05)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )

    assert str(bar_type) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TimeoutError)
    assert fake.events == ["connect", "aclose"]


def test_request_bars_converts_a_dead_connect_into_a_named_error() -> None:
    class _NeverConnects(_FakeHistoricClient):
        async def connect(self) -> None:
            await asyncio.sleep(3600)

    fake = _NeverConnects(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake, call_deadline=0.05)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.NASDAQ"), "1D")

    with pytest.raises(IbkrRequestError):
        provider.request_bars(
            bar_type,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
        )


def test_request_instruments_converts_a_stuck_qualification_into_a_named_error() -> (
    None
):
    class _StuckQualification(_FakeHistoricClient):
        async def request_instruments(self, **kwargs: Any) -> list[Any]:
            await asyncio.sleep(3600)
            return []

    fake = _StuckQualification(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake, call_deadline=0.05)

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_instruments((InstrumentId.from_str("VUSA.XLON"),))

    assert "VUSA.XLON" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TimeoutError)


def test_request_instruments_wraps_a_failed_qualification_in_a_named_error() -> None:
    """The opaque-crash case: a failed contract qualification (modelled by the
    adapter's ``int``-vs-``None`` reconnect ``TypeError``) becomes a clear error
    naming the instrument, instead of leaking the bare ``TypeError``."""

    class _Boom(_FakeHistoricClient):
        async def request_instruments(self, **kwargs: Any) -> list[Any]:
            raise TypeError(
                "'<=' not supported between instances of 'int' and 'NoneType'"
            )

    fake = _Boom(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)
    eur_usd = InstrumentId.from_str("EUR/USD.IDEALPRO")

    with pytest.raises(IbkrRequestError) as excinfo:
        provider.request_instruments((eur_usd,))

    assert "EUR/USD.IDEALPRO" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, TypeError)
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
    deferred to call time, so non-IBKR code does not initialize the vendor stack."""
    for module_name in tuple(sys.modules):
        if module_name == "aegis_data.ibkr" or module_name.startswith(
            "aegis_data.ibkr."
        ):
            sys.modules.pop(module_name)
        if module_name == "ibapi" or module_name.startswith("ibapi."):
            sys.modules.pop(module_name)

    import aegis_data.ibkr  # noqa: F401 — import-for-effect

    assert "ibapi" not in sys.modules


# --------------------------------------------------------------------------- #
# live-client gateway-mode seam (no ibapi: pure port -> Nautilus trading mode)
# --------------------------------------------------------------------------- #


def test_trading_mode_for_port_maps_ib_gateway_ports() -> None:
    from aegis_data.ibkr.live import _trading_mode_for_port

    assert _trading_mode_for_port(4002) == "paper"
    assert _trading_mode_for_port(4001) == "live"


def test_trading_mode_for_port_rejects_any_other_port() -> None:
    from aegis_data.ibkr.live import _trading_mode_for_port

    with pytest.raises(
        ValueError,
        match=r"IB_PORT must be 4002 \(paper\) or 4001 \(live\).*7497",
    ):
        _trading_mode_for_port(7497)


class _Instr:
    def __init__(self, instrument_id: InstrumentId) -> None:
        self.id = instrument_id


class _IneligibilityReasonLike:
    pass


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


def test_request_instruments_can_pass_expired_future_contracts() -> None:
    esm6 = InstrumentId.from_str("ESM6.XCME")
    fetched = [_Instr(esm6)]
    fake = _FakeHistoricClient(bars=[], instruments=fetched)
    provider = IbkrHistoricalProvider(
        include_expired_futures=True,
        client_factory=lambda: fake,
    )

    out = provider.request_instruments((esm6,))

    assert list(out) == fetched
    call = fake.instrument_calls[0]
    assert "instrument_ids" not in call
    contract = call["contracts"][0]
    assert contract.secType == "FUT"
    assert contract.exchange == "CME"
    assert contract.localSymbol == "ESM6"
    assert contract.includeExpired is True


def test_request_instruments_splits_expired_futures_from_plain_ids() -> None:
    esm6 = InstrumentId.from_str("ESM6.XCME")
    aapl = InstrumentId.from_str("AAPL.XNAS")

    class _SplitFake(_FakeHistoricClient):
        async def request_instruments(self, **kwargs: Any) -> list[Any]:
            self.instrument_calls.append(kwargs)
            if "instrument_ids" in kwargs:
                return [_Instr(aapl)]
            return [_Instr(esm6)]

    fake = _SplitFake(bars=[], instruments=[])
    provider = IbkrHistoricalProvider(
        include_expired_futures=True,
        client_factory=lambda: fake,
    )

    out = provider.request_instruments((aapl, esm6))

    assert [instrument.id for instrument in out] == [aapl, esm6]
    assert fake.instrument_calls[0]["instrument_ids"] == ["AAPL.XNAS"]
    contract = fake.instrument_calls[1]["contracts"][0]
    assert contract.secType == "FUT"
    assert contract.localSymbol == "ESM6"
    assert contract.includeExpired is True


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


def test_seed_strips_ibkr_ineligibility_reasons_before_catalog_write(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    gld = InstrumentId.from_str("GLD.ARCX")
    fetched = [
        Equity(
            instrument_id=gld,
            raw_symbol=Symbol("GLD"),
            currency=USD,
            price_precision=2,
            price_increment=Price.from_str("0.01"),
            lot_size=Quantity.from_int(100),
            ts_event=0,
            ts_init=0,
            info={
                "ineligibilityReasons": [_IneligibilityReasonLike()],
                "serializable": "kept",
            },
        )
    ]
    fake = _FakeHistoricClient(bars=[], instruments=fetched)
    provider = IbkrHistoricalProvider(client_factory=lambda: fake)

    seed_instrument_definitions(catalog, provider, (gld,))

    loaded = catalog.instruments(instrument_ids=[gld.value])
    assert [instrument.id for instrument in loaded] == [gld]
    assert loaded[0].info == {"serializable": "kept"}
