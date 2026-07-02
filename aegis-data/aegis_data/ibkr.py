"""The single IBKR adapter — research historic fetch *and* live client wiring
(ADR-0003 amendment / ADR-0006/0008).

One seam for IBKR: research and live connect to Interactive Brokers through this
module, so the unified path (epic ``aegis-rd-r8b``) depends on the Nautilus
DataProvider port with IBKR as its first — and only — adapter.

Two responsibilities behind one lazy ``ibapi`` boundary:

- **Historic fetch** (research / backfill): :class:`IbkrHistoricalProvider` wraps
  Nautilus's standalone ``HistoricInteractiveBrokersClient`` — the client "for
  backtesting and research".  It is **pure fetch** (``request_bars`` *returns*
  bars; :class:`CatalogBackedDataPort` is the single writer of record, ADR-0008),
  **hides ``asyncio``** behind a synchronous port, and resolves identity through
  IB **simplified symbology** — the native ``InstrumentId`` value
  (``SYMBOL.VENUE``) is the IBKR request id (ADR-0005).
- **Live client wiring**: :func:`attach_live_clients` builds Nautilus's *stock*
  ``InteractiveBrokers{Data,Exec}ClientConfig`` with a Nautilus-managed
  Dockerized IB Gateway and registers the stock live factories on a live
  ``TradingNode`` — no custom adapter code or container lifecycle code (epic
  thesis).  The Trader's broker-neutral ``node.py`` reaches IBKR through this
  one call.

IBKR (``ibapi``) is a true-external dependency, so *every* IBKR import — the
historic client and the live config/factory classes alike — is lazy: importing
this module never requires ``ibapi``.  Instrument *definitions* are a separate
Step-1 write (:func:`seed_instrument_definitions`), not per-window fill data
(ADR-0008).
"""

from __future__ import annotations

import asyncio
import atexit
import itertools
import math
import threading
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

import msgspec
import pandas as pd
from nautilus_trader.common.config import msgspec_encoding_hook
from nautilus_trader.model.identifiers import InstrumentId

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.instruments import Instrument

# IB Gateway defaults (paper port); the operator overrides for a live gateway.
IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 1
IB_MARKET_DATA_TYPE = "REALTIME"
IB_REQUEST_TIMEOUT = 120

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
    the cause.  Per-request *latency* on a no-data fetch (IB error 162) is bounded by
    the underlying client's request timeout — internal to the vendor adapter — so
    this clarifies the failure, it does not pre-empt that wait.
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
    ) -> Sequence[Bar]:
        """The vendor-aggregated bars for *bar_type* over ``[start, end]``."""
        return self._request(
            f"historical bars {bar_type}",
            lambda session: session.request_bars(
                bar_specifications=[str(bar_type.spec)],
                start_date_time=_naive_utc(start),
                end_date_time=_naive_utc(end),
                tz_name="UTC",
                instrument_ids=[bar_type.instrument_id.value],
                use_rth=self.use_rth,
                timeout=self.timeout,
            ),
        )

    def request_instruments(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> Sequence[Instrument]:
        """The IBKR instrument definitions for *instrument_ids* (Step-1 write)."""
        return self._request(
            "instrument definitions "
            f"[{', '.join(instrument_id.value for instrument_id in instrument_ids)}]",
            lambda session: session.request_instruments(
                instrument_ids=[
                    instrument_id.value for instrument_id in instrument_ids
                ],
            ),
        )

    def request_adjusted_last(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        primary_exchange: str | None = None,
        currency: str = "USD",
    ) -> pd.Series:
        """The raw-``ibapi`` daily ``ADJUSTED_LAST`` close series.

        Nautilus' historic bar path cannot express IBKR's ``ADJUSTED_LAST``
        ``whatToShow`` value, so this one derivation source uses a deliberately
        narrow raw-IB seam.  Normal production ``TRADES`` bars still ride
        :meth:`request_bars` through the generic data-provider port.
        """
        subject = f"ADJUSTED_LAST closes {instrument_id.value}"
        try:
            rows = self._adjusted_last_client().request_daily_closes(
                instrument_id=instrument_id,
                what_to_show="ADJUSTED_LAST",
                start=start,
                end=end,
                primary_exchange=primary_exchange,
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
        await session.connect()
        try:
            return await call(session)
        finally:
            await session.aclose()

    def _connection(self) -> tuple[Any, Any]:
        if not _IB_CONNECTION:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            session = self._build_real_session()
            loop.run_until_complete(session.connect())
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
        primary_exchange: str | None,
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
    primary_exchange: str | None,
    currency: str,
) -> Any:
    from ibapi.contract import Contract

    contract = Contract()
    contract.symbol = instrument_id.symbol.value
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.primaryExchange = primary_exchange or instrument_id.venue.value
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


# ── Live client wiring ───────────────────────────────────────────────────────

# Nautilus client name shared by the IBKR data + exec clients (the key the
# registered factories resolve against).
IB_CLIENT_NAME = "INTERACTIVE_BROKERS"


class BrokerConnection(Protocol):
    """The Trader-owned Broker Connection this adapter translates into IBKR
    client configs (the connection value object lives in the Trader; this adapter
    depends only on its shape, never imports it — DIP).

    The Trader stays broker-neutral and supplies only the gateway port/account
    facts.  This adapter is the only place that maps IBKR's paper/live ports to
    Nautilus's dockerized ``trading_mode`` spelling.
    """

    port: int
    client_id: int
    account_id: str


def attach_live_clients(
    node: Any,
    connection: BrokerConnection,
    instrument_ids: Sequence[InstrumentId],
) -> None:
    """Wire IBKR's stock live data + exec clients onto *node* (before ``build()``).

    The single live-broker call the Trader's broker-neutral ``node.py`` makes:
    builds Nautilus's *stock* ``InteractiveBrokers{Data,Exec}ClientConfig`` —
    ``market_data_type=REALTIME``, a Nautilus-managed Dockerized IB Gateway, and
    an ``InstrumentProviderConfig`` whose ``load_ids`` are exactly the declared
    native ids (the data-only FX ``exchange:`` natives ride in here too) — and
    registers the stock live factories.  No custom adapter code: paper vs live is
    *only* ``connection.port``, translated here into the dockerized
    ``trading_mode``.

    The ibapi-backed config/factory classes are imported lazily so importing this
    module never needs ``ibapi`` (the same lazy boundary as the historic client).
    """
    import msgspec
    from nautilus_trader.adapters.interactive_brokers.config import (
        IBMarketDataTypeEnum,
        InteractiveBrokersDataClientConfig,
        InteractiveBrokersExecClientConfig,
    )
    from nautilus_trader.adapters.interactive_brokers.factories import (
        InteractiveBrokersLiveDataClientFactory,
        InteractiveBrokersLiveExecClientFactory,
    )

    provider = mic_instrument_provider_config(
        load_ids=(instrument_id.value for instrument_id in instrument_ids),
    )
    endpoint = _gateway_endpoint(connection)
    data_config = InteractiveBrokersDataClientConfig(
        ibg_client_id=connection.client_id,
        market_data_type=IBMarketDataTypeEnum.REALTIME,
        use_regular_trading_hours=True,
        instrument_provider=provider,
        **endpoint,
    )
    exec_config = InteractiveBrokersExecClientConfig(
        ibg_client_id=connection.client_id,
        account_id=connection.account_id,
        instrument_provider=provider,
        **endpoint,
    )
    # Nautilus consumes ``data_clients``/``exec_clients`` from the node's stored
    # config at ``build()``; there is no public setter, so swap the (immutable)
    # config for one carrying the IBKR clients, then register the factories.
    node._config = msgspec.structs.replace(
        node._config,
        data_clients={IB_CLIENT_NAME: data_config},
        exec_clients={IB_CLIENT_NAME: exec_config},
    )
    node.add_data_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveExecClientFactory)


def mic_instrument_provider_config(load_ids: Iterable[str] | None = None) -> Any:
    """The IBKR instrument-provider config with the venue pin (r8b.9 Slice F(b)).

    ``convert_exchange_to_mic_venue=True`` qualifies IBKR exchanges to their MIC venues
    (``CME → XCME``, ``NYBOT → IFUS``; gateway probe ``resolved-r8b-9-probe6-ice-venue``),
    so every IBKR contract — a static native, a live subscription, or a discovered
    futures-chain leg — resolves to ONE deterministic venue.  The synthetic continuous-root
    id ``{root}.{venue}`` then inherits it and aegis-data's single-venue chain build holds.
    Shared by the live wiring (:func:`attach_live_clients`) and the historic seed/backfill so
    both sides mint byte-identical ids.  Lazily imports the ibapi-backed config, preserving
    the module's lazy-``ibapi`` boundary.
    """
    from nautilus_trader.adapters.interactive_brokers.config import (
        InteractiveBrokersInstrumentProviderConfig,
    )

    kwargs: dict[str, Any] = {"convert_exchange_to_mic_venue": True}
    if load_ids is not None:
        kwargs["load_ids"] = frozenset(load_ids)
    return InteractiveBrokersInstrumentProviderConfig(**kwargs)


_GATEWAY_TRADING_MODE: dict[int, Literal["paper", "live"]] = {
    4002: "paper",
    4001: "live",
}


def _trading_mode_for_port(port: int) -> Literal["paper", "live"]:
    try:
        return _GATEWAY_TRADING_MODE[port]
    except KeyError as exc:
        raise ValueError(
            "IB_PORT must be 4002 (paper) or 4001 (live) for the dockerized "
            f"gateway; got {port}"
        ) from exc


def _gateway_endpoint(connection: BrokerConnection) -> dict[str, Any]:
    """The Dockerized IB Gateway kwargs shared by both IBKR client configs."""
    from nautilus_trader.adapters.interactive_brokers.config import (
        DockerizedIBGatewayConfig,
    )

    gateway = DockerizedIBGatewayConfig(
        trading_mode=_trading_mode_for_port(connection.port),
        read_only_api=False,
    )
    return {"dockerized_gateway": gateway}


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


__all__ = [
    "IB_CLIENT_NAME",
    "BrokerConnection",
    "IbkrHistoricalProvider",
    "IbkrRequestError",
    "attach_live_clients",
    "close_connection",
    "mic_instrument_provider_config",
    "seed_instrument_definitions",
]
