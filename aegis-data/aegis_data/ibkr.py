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
  ``InteractiveBrokers{Data,Exec}ClientConfig`` and registers the stock live
  factories on a live ``TradingNode`` — no custom adapter code (epic thesis).
  The Trader's broker-neutral ``node.py`` reaches IBKR through this one call.

IBKR (``ibapi``) is a true-external dependency, so *every* IBKR import — the
historic client and the live config/factory classes alike — is lazy: importing
this module never requires ``ibapi``.  Instrument *definitions* are a separate
Step-1 write (:func:`seed_instrument_definitions`), not per-window fill data
(ADR-0008).
"""

from __future__ import annotations

import asyncio
import atexit
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
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
        return self._run(
            lambda session: session.request_bars(
                bar_specifications=[str(bar_type.spec)],
                start_date_time=_naive_utc(start),
                end_date_time=_naive_utc(end),
                tz_name="UTC",
                instrument_ids=[bar_type.instrument_id.value],
                use_rth=self.use_rth,
                timeout=self.timeout,
            )
        )

    def request_instruments(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> Sequence[Instrument]:
        """The IBKR instrument definitions for *instrument_ids* (Step-1 write)."""
        return self._run(
            lambda session: session.request_instruments(
                instrument_ids=[
                    instrument_id.value for instrument_id in instrument_ids
                ],
            )
        )

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
            )
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

    ``dockerized_gateway`` is the seam for the Dockerized paper/live daemon
    (bd ``aegis-rd-r8b.6``): when set, the gateway supplies the endpoint and the
    explicit ``host``/``port`` are omitted; it is ``None`` in the skeleton.
    """

    host: str
    port: int
    client_id: int
    account_id: str
    dockerized_gateway: Any | None


def attach_live_clients(
    node: Any,
    connection: BrokerConnection,
    instrument_ids: Sequence[InstrumentId],
) -> None:
    """Wire IBKR's stock live data + exec clients onto *node* (before ``build()``).

    The single live-broker call the Trader's broker-neutral ``node.py`` makes:
    builds Nautilus's *stock* ``InteractiveBrokers{Data,Exec}ClientConfig`` —
    ``market_data_type=REALTIME`` and an ``InstrumentProviderConfig`` whose
    ``load_ids`` are exactly the declared native ids (the data-only FX ``exchange:``
    natives ride in here too) — and registers the stock live factories.  No custom
    adapter code: paper vs live is *only* ``connection.port`` (IBKR's own guidance).

    The ibapi-backed config/factory classes are imported lazily so importing this
    module never needs ``ibapi`` (the same lazy boundary as the historic client).
    """
    import msgspec
    from nautilus_trader.adapters.interactive_brokers.config import (
        IBMarketDataTypeEnum,
        InteractiveBrokersDataClientConfig,
        InteractiveBrokersExecClientConfig,
        InteractiveBrokersInstrumentProviderConfig,
    )
    from nautilus_trader.adapters.interactive_brokers.factories import (
        InteractiveBrokersLiveDataClientFactory,
        InteractiveBrokersLiveExecClientFactory,
    )

    provider = InteractiveBrokersInstrumentProviderConfig(
        load_ids=frozenset(instrument_id.value for instrument_id in instrument_ids),
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


def _gateway_endpoint(connection: BrokerConnection) -> dict[str, Any]:
    """The endpoint kwargs shared by both IBKR client configs.

    Dockerized seam (bd ``aegis-rd-r8b.6``): a ``dockerized_gateway`` supplies its
    own host/port, so the two are mutually exclusive.  The skeleton always takes
    the explicit-endpoint branch (the gateway is ``None``)."""
    gateway = connection.dockerized_gateway
    if gateway is not None:
        return {"dockerized_gateway": gateway}
    return {"ibg_host": connection.host, "ibg_port": connection.port}


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
        catalog.write_data(list(instruments))


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


__all__ = [
    "IB_CLIENT_NAME",
    "BrokerConnection",
    "IbkrHistoricalProvider",
    "attach_live_clients",
    "close_connection",
    "seed_instrument_definitions",
]
