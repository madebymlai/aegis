"""IBKR historic fetch — the DataProvider adapter for research and backfill.

:class:`IbkrHistoricalProvider` is pure fetch behind the Nautilus DataProvider
port (``request_bars`` *returns* bars; :class:`CatalogBackedDataPort` is the
single writer of record, ADR-0008), hides ``asyncio`` behind a synchronous
surface, and resolves identity through IB simplified symbology (ADR-0005).
The raw-``ibapi`` ``ADJUSTED_LAST`` machinery and the process-singleton
connection live here with it; :func:`seed_instrument_definitions` is the
separate Step-1 definition write.  Every ``ibapi``/Nautilus-adapter import is
lazy — importing this module never requires ``ibapi``.
"""

from __future__ import annotations

import asyncio
import atexit
import itertools
import math
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import msgspec
import pandas as pd
from nautilus_trader.common.config import msgspec_encoding_hook
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import ServedBars
from aegis_data.ibkr.symbology import mic_instrument_provider_config

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.instruments import Instrument

# IB Gateway defaults (paper port); the operator overrides for a live gateway.
IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 1
IB_MARKET_DATA_TYPE = "REALTIME"
IB_REQUEST_TIMEOUT = 120
# The dead-call line: any single await on the vendor session that makes no
# progress for this long is stuck, not slow (the vendor stack has unbounded
# awaits — connect, shared-request futures — that otherwise hang forever, #75).
IB_CALL_DEADLINE = 600

# IB ``MarketDataTypeEnum`` member names — validated up front so a bad value fails
# at construction, not at connect time, without importing ``ibapi`` to do it.
_IB_MARKET_DATA_TYPES = frozenset({"REALTIME", "FROZEN", "DELAYED", "DELAYED_FROZEN"})

# Nautilus initializes a **process-global** Rust logger when an IB client is
# constructed, so a second client in the same process aborts
# ("attempted to set a logger after the logging system was already initialized").
# The real connection is therefore a per-process singleton (one loop + one client),
# created once and reused by every call across every provider instance.
_IB_CONNECTION: dict[str, Any] = {}
_RAW_CLIENT_ID_SEQUENCE = itertools.count(1)


class IbkrRequestError(RuntimeError):
    """A historic IBKR fetch could not complete, named by its subject.

    A fetch can fail deep in the asyncio/Nautilus stack — a dropped or lost gateway
    connection (IB code 1100), a per-request timeout, or a failed contract
    qualification — and those surface as bare, context-free errors (notably an
    ``int``-vs-``None`` ``TypeError`` from the adapter's reconnect path).  The
    provider translates them into this one error so a caller learns *which* fetch
    failed and *why*, rather than an opaque stack trace; the original is chained as
    the cause.  The vendor stack also has genuinely unbounded awaits (connect,
    shared-request futures, stuck qualification of an instrument that cannot
    resolve to one asset) — every session await is therefore deadline-bounded
    (``call_deadline``), so a dead call surfaces here instead of hanging (#75).
    """


@dataclass(frozen=True)
class IbkrHistoricalProvider:
    """Pure-fetch IBKR data provider over the standalone historic client.

    Connection management is dictated by an upstream constraint: only one IB client
    may exist per process (it sets up a process-global Rust logger).  So the real
    connection is a **process singleton** — one persistent event loop and one
    connected client, lazily created and reused by every ``request_*`` call across
    all provider instances; per-call connect/teardown would abort on the second
    call.  Connection params come from the *first* provider that opens it.

    ``client_factory`` exists for testing: a fake session stands in for the real
    client (it has no process-global constraint, so it runs isolated per call), so
    the param-translation and asyncio-hiding are verified without IBKR.
    """

    host: str = IB_HOST
    port: int = IB_PORT
    client_id: int = IB_CLIENT_ID
    market_data_type: str = IB_MARKET_DATA_TYPE
    use_rth: bool = True
    timeout: int = IB_REQUEST_TIMEOUT
    call_deadline: float = IB_CALL_DEADLINE
    include_expired_futures: bool = False
    client_factory: Callable[[], Any] | None = None
    adjusted_last_client_factory: Callable[[], Any] | None = None

    def __post_init__(self) -> None:
        if self.market_data_type not in _IB_MARKET_DATA_TYPES:
            raise ValueError(
                f"unknown IB market_data_type {self.market_data_type!r}; "
                f"expected one of {sorted(_IB_MARKET_DATA_TYPES)}"
            )

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedBars:
        """The vendor-aggregated bars for *bar_type* over ``[start, end]``.

        The window is walked newest-first in ≤365-day chunks (one IB historic
        request each) and the walk **stops at the no-data wall**: the first chunk
        that comes back empty means the window has stepped past the instrument's
        available history, so earlier chunks are never requested (#75) — each one
        would only burn a full request timeout to learn the same thing.  The
        answer carries the bars *and* ``served_from`` (how far back the walk got)
        so the port claims coverage honestly; judging whether the shortfall is
        acceptable stays with the catalog's coverage gate.
        """
        contract = self._expired_future_contract(bar_type.instrument_id)
        instrument_kwargs = (
            {"contracts": [contract]}
            if contract is not None
            else {"instrument_ids": [bar_type.instrument_id.value]}
        )
        return self._request(
            f"historical bars {bar_type}",
            lambda session: self._walk_bars_to_the_wall(
                session,
                bar_type=bar_type,
                start=start,
                end=end,
                instrument_kwargs=instrument_kwargs,
            ),
        )

    async def _walk_bars_to_the_wall(
        self,
        session: Any,
        *,
        bar_type: BarType,
        start: pd.Timestamp,
        end: pd.Timestamp,
        instrument_kwargs: Mapping[str, Any],
    ) -> ServedBars:
        bars: list[Bar] = []
        for chunk_start, chunk_end in _backward_windows(start, end):
            pulled = await asyncio.wait_for(
                session.request_bars(
                    bar_specifications=[str(bar_type.spec)],
                    start_date_time=_naive_utc(chunk_start),
                    end_date_time=_naive_utc(chunk_end),
                    tz_name="UTC",
                    use_rth=self.use_rth,
                    timeout=self.timeout,
                    **instrument_kwargs,
                ),
                timeout=self.call_deadline,
            )
            if not pulled:
                # The wall.  Its truth boundary is day-precise for free: the
                # oldest data-bearing chunk was queried in full, so its first
                # bar IS where the source's history begins — everything from
                # that instant on was served, nothing before it exists.
                return ServedBars(tuple(bars), _first_bar_instant(bars, end))
            bars = list(pulled) + bars
        return ServedBars(tuple(bars), start)

    def request_instruments(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> Sequence[Instrument]:
        """The IBKR instrument definitions for *instrument_ids* (Step-1 write)."""
        plain_ids, contracts = self._instrument_request_parts(instrument_ids)
        return self._request(
            "instrument definitions "
            f"[{', '.join(instrument_id.value for instrument_id in instrument_ids)}]",
            lambda session: _request_instrument_parts(
                session, plain_ids, contracts, deadline=self.call_deadline
            ),
        )

    def request_adjusted_last(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        currency: str = "USD",
    ) -> pd.Series:
        """The raw-``ibapi`` daily ``ADJUSTED_LAST`` close series.

        Nautilus' historic bar path cannot express IBKR's ``ADJUSTED_LAST``
        ``whatToShow`` value, so this one derivation source uses a deliberately
        narrow raw-IB seam.  Normal production ``TRADES`` bars still ride
        :meth:`request_bars` through the generic data-provider port.  The IB
        ``primaryExchange`` is derived here from the instrument's corpus venue
        (vendor symbology is the provider's secret, ADR-0005): callers name the
        instrument, never an exchange.
        """
        subject = f"ADJUSTED_LAST closes {instrument_id.value}"
        try:
            rows = self._adjusted_last_client().request_daily_closes(
                instrument_id=instrument_id,
                what_to_show="ADJUSTED_LAST",
                start=start,
                end=end,
                primary_exchange=_ib_primary_exchange(instrument_id),
                currency=currency,
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - any IB/raw socket fault -> one named error
            raise IbkrRequestError(
                f"IBKR could not fetch {subject}: {type(exc).__name__}: {exc}"
            ) from exc
        if not rows:
            return pd.Series(dtype=float)
        index = pd.DatetimeIndex([timestamp for timestamp, _close in rows])
        return pd.Series([close for _timestamp, close in rows], index=index).sort_index()

    def _request(self, subject: str, call: Callable[[Any], Awaitable[Any]]) -> Any:
        """Run an IBKR fetch, surfacing any fault as a named :class:`IbkrRequestError`.

        The single fault boundary for the historic client: a connection drop, a
        timeout, or a failed qualification arrives as a bare asyncio/Nautilus error
        with no context (e.g. an ``int``-vs-``None`` reconnect ``TypeError``).
        Re-raising it as one error named by *subject*, with the original chained,
        tells the caller which fetch failed and why.  ``BaseException``
        (``KeyboardInterrupt``, ``CancelledError``) is left to propagate untouched.
        """
        try:
            return self._run(call)
        except Exception as exc:  # noqa: BLE001 - any IB/asyncio fault -> one clear error
            raise IbkrRequestError(
                f"IBKR could not fetch {subject}: {type(exc).__name__}: {exc}"
            ) from exc

    def _run(self, call: Callable[[Any], Awaitable[Any]]) -> Any:
        if self.client_factory is not None:
            return asyncio.run(self._isolated(self.client_factory, call))
        loop, session = self._connection()
        return loop.run_until_complete(call(session))

    async def _isolated(
        self, make: Callable[[], Any], call: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        # Test path only: the fake session has no process-global constraint, so it
        # connects, runs, and closes per call in its own loop.
        session = make()
        await asyncio.wait_for(session.connect(), timeout=self.call_deadline)
        try:
            return await call(session)
        finally:
            await session.aclose()

    def _connection(self) -> tuple[Any, Any]:
        if not _IB_CONNECTION:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            session = self._build_real_session()
            loop.run_until_complete(
                asyncio.wait_for(session.connect(), timeout=self.call_deadline)
            )
            _IB_CONNECTION["loop"] = loop
            _IB_CONNECTION["session"] = session
        return _IB_CONNECTION["loop"], _IB_CONNECTION["session"]

    def _build_real_session(self) -> _HistoricSession:
        from ibapi.common import MarketDataTypeEnum
        from nautilus_trader.adapters.interactive_brokers.historical.client import (
            HistoricInteractiveBrokersClient,
        )

        return _HistoricSession(
            HistoricInteractiveBrokersClient(
                host=self.host,
                port=self.port,
                client_id=self.client_id,
                market_data_type=getattr(MarketDataTypeEnum, self.market_data_type),
                instrument_provider_config=mic_instrument_provider_config(),
            )
        )

    def _adjusted_last_client(self) -> Any:
        if self.adjusted_last_client_factory is not None:
            return self.adjusted_last_client_factory()
        return _IbapiDailyCloseClient(
            host=self.host,
            port=self.port,
            client_id=self.client_id + 7_000 + next(_RAW_CLIENT_ID_SEQUENCE),
            use_rth=self.use_rth,
        )

    def _instrument_request_parts(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> tuple[list[str], list[Any]]:
        plain_ids: list[str] = []
        contracts: list[Any] = []
        for instrument_id in instrument_ids:
            contract = self._expired_future_contract(instrument_id)
            if contract is None:
                plain_ids.append(instrument_id.value)
            else:
                contracts.append(contract)
        return plain_ids, contracts

    def _expired_future_contract(self, instrument_id: InstrumentId) -> Any | None:
        if not self.include_expired_futures:
            return None
        return _expired_future_contract(instrument_id)


# One IB historic request serves at most this much history for daily bars; the
# backward walk steps in windows of this span.
_FETCH_CHUNK_SPAN = pd.Timedelta(days=365)
# Adjacent chunks abut one second apart — IB requests are second-granular, and no
# bar the corpus serves (daily) can fall inside the crack.
_CHUNK_GAP = pd.Timedelta(seconds=1)


def _first_bar_instant(bars: Sequence[Bar], fallback: pd.Timestamp) -> pd.Timestamp:
    """Where served history begins: the oldest pulled bar's event time, or
    *fallback* when nothing was pulled at all (nothing is claimed either way)."""
    if not bars:
        return fallback
    return pd.Timestamp(bars[0].ts_event, tz="UTC")


def _backward_windows(
    start: pd.Timestamp, end: pd.Timestamp
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """``[start, end]`` as newest-first chunk windows for the wall-stopping walk."""
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    chunk_end = end
    while chunk_end > start:
        chunk_start = max(start, chunk_end - _FETCH_CHUNK_SPAN)
        windows.append((chunk_start, chunk_end))
        chunk_end = chunk_start - _CHUNK_GAP
    return windows


async def _request_instrument_parts(
    session: Any,
    plain_ids: Sequence[str],
    contracts: Sequence[Any],
    *,
    deadline: float,
) -> list[Instrument]:
    # Each vendor await is deadline-bounded: an instrument that cannot resolve to
    # one asset can leave the qualification machinery stuck instead of erroring,
    # and a dead await must surface as an IbkrRequestError, not a hang (#75).
    instruments: list[Instrument] = []
    if plain_ids:
        instruments.extend(
            await asyncio.wait_for(
                session.request_instruments(instrument_ids=list(plain_ids)),
                timeout=deadline,
            )
        )
    if contracts:
        instruments.extend(
            await asyncio.wait_for(
                session.request_instruments(contracts=list(contracts)),
                timeout=deadline,
            )
        )
    return instruments


def _ib_primary_exchange(instrument_id: InstrumentId) -> str:
    """The IB exchange code for an instrument's corpus (MIC) venue.

    The corpus pins MIC venues (``XAMS``), but IB contracts only accept IB's own
    exchange codes (``AEB``) — a MIC as ``primaryExchange`` is rejected with IB
    error 200 "exchange invalid".  A venue with no MIC mapping (``ARCA``) is
    already an IB code and passes through unchanged.
    """
    from nautilus_trader.adapters.interactive_brokers.parsing.instruments import (
        possible_exchanges_for_venue,
    )

    return possible_exchanges_for_venue(instrument_id.venue.value)[0]


def _expired_future_contract(instrument_id: InstrumentId) -> Any | None:
    from nautilus_trader.adapters.interactive_brokers.parsing.instruments import (
        instrument_id_to_ib_contract,
        possible_exchanges_for_venue,
    )

    for exchange in possible_exchanges_for_venue(instrument_id.venue.value):
        try:
            contract = instrument_id_to_ib_contract(instrument_id, exchange)
        except ValueError:
            continue
        if contract.secType == "FUT":
            return msgspec.structs.replace(contract, includeExpired=True)
        return None
    return None


class _HistoricSession:
    """Anti-corruption wrapper over ``HistoricInteractiveBrokersClient``.

    The historic client exposes a connect-only public surface — no teardown and no
    context manager — so this adapts it to a uniform ``connect`` / ``request_*`` /
    ``aclose`` session, driving the inner client's connection lifecycle on close
    (the only available teardown).  Isolating that one private reach here keeps the
    provider testable against a clean session interface.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def connect(self) -> None:
        await self._client.connect()

    async def request_bars(self, **kwargs: Any) -> Sequence[Bar]:
        return await self._client.request_bars(**kwargs)

    async def request_instruments(self, **kwargs: Any) -> Sequence[Instrument]:
        return await self._client.request_instruments(**kwargs)

    async def aclose(self) -> None:
        # The historic client has no public teardown; stopping the inner client
        # drains its background tasks cleanly (so closing the loop is quiet).
        await self._client._client._stop_async()


@dataclass(frozen=True)
class _IbapiDailyCloseClient:
    """Small raw-``ibapi`` client for daily ``whatToShow`` close series."""

    host: str
    port: int
    client_id: int
    use_rth: bool

    def request_daily_closes(
        self,
        *,
        instrument_id: InstrumentId,
        what_to_show: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        primary_exchange: str,
        currency: str,
        timeout: int,
    ) -> list[tuple[pd.Timestamp, float]]:
        app = _build_raw_historical_app()
        app.connect(self.host, self.port, clientId=self.client_id)
        threading.Thread(target=app.run, daemon=True).start()
        if not app.ready.wait(timeout=15):
            app.disconnect()
            raise TimeoutError("IBKR raw client did not receive nextValidId")
        req_id = 1
        app.reqHistoricalData(
            reqId=req_id,
            contract=_stock_contract(
                instrument_id,
                primary_exchange=primary_exchange,
                currency=currency,
            ),
            endDateTime=_ib_request_end_datetime(what_to_show, end),
            durationStr=_ib_request_duration(what_to_show, start, end),
            barSizeSetting="1 day",
            whatToShow=what_to_show,
            useRTH=1 if self.use_rth else 0,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[],
        )
        deadline = time.time() + timeout
        while time.time() < deadline and req_id not in app.done:
            time.sleep(0.05)
        app.disconnect()
        if req_id not in app.done:
            raise TimeoutError(f"IBKR raw {what_to_show} request timed out")
        if app.errors.get(req_id) and not app.bars.get(req_id):
            raise RuntimeError("; ".join(app.errors[req_id]))
        return _bounded_daily_closes(app.bars.get(req_id, []), start=start, end=end)


def _build_raw_historical_app() -> Any:
    from collections import defaultdict

    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper

    class _RawHistoricalApp(EWrapper, EClient):
        def __init__(self) -> None:
            EClient.__init__(self, self)
            self.bars: dict[int, list[tuple[str, float]]] = defaultdict(list)
            self.done: set[int] = set()
            self.errors: dict[int, list[str]] = defaultdict(list)
            self.ready = threading.Event()

        def nextValidId(self, orderId: int) -> None:  # noqa: N802, ARG002
            self.ready.set()

        def historicalData(self, reqId, bar) -> None:  # noqa: N802, ANN001
            self.bars[reqId].append((bar.date, float(bar.close)))

        def historicalDataEnd(self, reqId, start, end) -> None:  # noqa: N802, ANN001, ARG002
            self.done.add(reqId)

        def error(self, reqId, *args) -> None:  # noqa: ANN001
            msg = " ".join(str(arg) for arg in args)
            if reqId is not None and reqId >= 0:
                self.errors[reqId].append(msg)
                if any(code in msg for code in ("354", "10167", "162", "200", "165", "321")):
                    self.done.add(reqId)

    return _RawHistoricalApp()


def _stock_contract(
    instrument_id: InstrumentId,
    *,
    primary_exchange: str,
    currency: str,
) -> Any:
    from ibapi.contract import Contract

    contract = Contract()
    contract.symbol = instrument_id.symbol.value
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.primaryExchange = primary_exchange
    contract.currency = currency.upper()
    return contract


def _ib_duration(start: pd.Timestamp, end: pd.Timestamp) -> str:
    days = max(1, math.ceil((_utc(end) - _utc(start)) / pd.Timedelta(days=1)))
    if days <= 365:
        return f"{days} D"
    return f"{math.ceil(days / 365)} Y"


def _ib_request_end_datetime(what_to_show: str, end: pd.Timestamp) -> str:
    if what_to_show.upper() == "ADJUSTED_LAST":
        return ""
    return _ib_datetime(end)


def _ib_request_duration(
    what_to_show: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> str:
    if what_to_show.upper() == "ADJUSTED_LAST":
        return _ib_duration(start, max(_utc(end), pd.Timestamp.now(tz="UTC")))
    return _ib_duration(start, end)


def _ib_datetime(timestamp: pd.Timestamp) -> str:
    return _utc(timestamp).strftime("%Y%m%d %H:%M:%S UTC")


def _bounded_daily_closes(
    rows: Sequence[tuple[str, float]],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[pd.Timestamp, float]]:
    start_ts = _utc(start)
    end_ts = _utc(end)
    bounded: list[tuple[pd.Timestamp, float]] = []
    for date_value, close in rows:
        timestamp = pd.Timestamp(str(date_value), tz="UTC")
        if start_ts <= timestamp <= end_ts:
            bounded.append((timestamp, close))
    return bounded


def _utc(timestamp: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        return value.tz_localize("UTC")
    return value.tz_convert("UTC")


def close_connection() -> None:
    """Tear down the process-singleton real session (idempotent, best-effort).

    Registered at process exit so a real connection closes cleanly; safe to call
    explicitly (e.g. test teardown).  Never raises — exit-time cleanup."""
    if not _IB_CONNECTION:
        return
    loop = _IB_CONNECTION["loop"]
    session = _IB_CONNECTION["session"]
    try:
        loop.run_until_complete(session.aclose())
    except Exception:  # noqa: BLE001 - exit-time cleanup must not raise
        pass
    finally:
        loop.close()
        _IB_CONNECTION.clear()


atexit.register(close_connection)


def _naive_utc(timestamp: pd.Timestamp) -> datetime:
    """A naive UTC ``datetime`` for the historic client, which applies ``tz_name``
    itself (``pd.Timestamp(value, tz=tz_name)``) and so rejects a tz-aware input."""
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def seed_instrument_definitions(
    catalog: Any,
    provider: IbkrHistoricalProvider,
    instrument_ids: Sequence[InstrumentId],
) -> None:
    """Persist instrument definitions to *catalog* (the Step-1 write, ADR-0008).

    Definitions are a **separate lifecycle** from the per-window bar fill — static
    setup, not windowed data (ADR-0008, ISP: the bar port is not widened). It is
    **idempotent**: only the definitions missing from *catalog* are fetched and
    written, so calling it is free when they are already present — which is what
    lets the lazy fill trigger it on a backfill without making a warm read connect
    to IBKR. The provider *fetches* definitions, aegis-data *writes* them.
    """
    missing = _missing_definitions(catalog, instrument_ids)
    if not missing:
        return
    instruments = provider.request_instruments(missing)
    if instruments:
        catalog.write_data(
            [_catalog_safe_instrument(instrument) for instrument in instruments]
        )


def _missing_definitions(
    catalog: Any, instrument_ids: Sequence[InstrumentId]
) -> list[InstrumentId]:
    present = {
        instrument.id
        for instrument in catalog.instruments(
            instrument_ids=[instrument_id.value for instrument_id in instrument_ids]
        )
    }
    return [instrument_id for instrument_id in instrument_ids if instrument_id not in present]


_DROP_INFO_VALUE = object()
_IBKR_PROVIDER_ONLY_INFO_KEYS = frozenset({"ineligibilityReasons"})


def _catalog_safe_instrument(instrument: Instrument) -> Instrument:
    if not hasattr(type(instrument), "to_dict") or not hasattr(
        type(instrument), "from_dict"
    ):
        return instrument
    values = type(instrument).to_dict(instrument)
    values["info"] = _catalog_safe_info(values.get("info"))
    return type(instrument).from_dict(values)


def _catalog_safe_info(info: Any) -> dict[str, Any] | None:
    if info is None:
        return None
    safe = _catalog_safe_info_value(info)
    return safe if isinstance(safe, dict) else {}


def _catalog_safe_info_value(value: Any) -> Any:
    if _catalog_info_encodable(value):
        return value
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in _IBKR_PROVIDER_ONLY_INFO_KEYS:
                continue
            safe_item = _catalog_safe_info_value(item)
            if safe_item is not _DROP_INFO_VALUE:
                safe[key_text] = safe_item
        return safe
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        safe_items = [
            safe_item
            for item in value
            if (safe_item := _catalog_safe_info_value(item)) is not _DROP_INFO_VALUE
        ]
        return safe_items
    return _DROP_INFO_VALUE


def _catalog_info_encodable(value: Any) -> bool:
    try:
        msgspec.json.encode(value, enc_hook=msgspec_encoding_hook)
    except TypeError:
        return False
    return True
