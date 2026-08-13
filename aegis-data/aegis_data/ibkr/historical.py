"""IBKR historic fetch — the DataProvider adapter for research and backfill.

:class:`IbkrHistoricalProvider` is pure fetch behind the Nautilus DataProvider
port (``request_bars`` *returns* bars; :class:`CatalogBackedDataPort` is the
single writer of record, ADR-0008), hides ``asyncio`` behind a synchronous
surface, and resolves identity through IB simplified symbology (ADR-0005).
The ``ADJUSTED_LAST`` extension and process-singleton connection live here with
it; :func:`seed_instrument_definitions` is the separate Step-1 definition write.
Every ``ibapi``/Nautilus-adapter import is lazy — importing this module never
requires ``ibapi``.
"""

from __future__ import annotations

import asyncio
import atexit
import functools
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import msgspec
import pandas as pd
from nautilus_trader.common.config import msgspec_encoding_hook
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import raw_bar_type
from aegis_data.provider import ProviderAnswer
from aegis_data.storage import Catalog
from aegis_data.ibkr.symbology import mic_instrument_provider_config

if TYPE_CHECKING:
    from nautilus_trader.adapters.interactive_brokers.common import IBContract
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
_ADJUSTED_LAST_WHAT_TO_SHOW = "ADJUSTED_LAST"

# Nautilus initializes a **process-global** Rust logger when an IB client is
# constructed, so a second client in the same process aborts
# ("attempted to set a logger after the logging system was already initialized").
# The real connection is therefore a per-process singleton (one loop + one client),
# created once and reused by every call across every provider instance.
_IB_CONNECTION: dict[str, Any] = {}


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


class _QualificationCardinalityError(ValueError):
    """Qualification did not return exactly one instrument."""


class _QualificationIdentityError(ValueError):
    """Qualification returned an instrument other than the requested identity."""


class _QualificationMetadataError(ValueError):
    """A qualified instrument did not carry a valid IB contract."""


class _QualificationConIdError(ValueError):
    """A qualified IB contract did not carry a positive contract ID."""


class _QualificationCurrencyError(ValueError):
    """A qualified IB contract used a currency other than the requested one."""


class _AdjustedLastRegistrationError(RuntimeError):
    """Nautilus could not register an adjusted-history request."""


class _AdjustedLastCompletionError(RuntimeError):
    """A registered Nautilus adjusted-history request did not complete."""


_PRESERVE_HISTORICAL_FAILURE: ContextVar[bool] = ContextVar(
    "preserve_historical_failure",
    default=False,
)


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
    ) -> ProviderAnswer[Bar]:
        """The vendor bars for *bar_type* over ``[start, end]`` in one native request.

        The whole window is asked for as a single IB ``duration`` ending at *end*.
        Nautilus segments an IB request by its duration internally, so the provider
        does not re-implement that walk; and IB clamps the answer at the instrument's
        earliest available data, so no request ever steps past the listing into empty
        pre-history — the job the old backward walk did with a no-data wall (#75),
        now done by IB itself in one request. ``oldest_verified`` reports how far back
        the answer reached: the requested *start* when history covers it (so a
        follow-on write abuts the prior file), or the oldest bar returned when IB
        clamped at a later listing (so the pre-history head stays unclaimed for the
        coverage gate).  A whole-unit duration overshoots below *start*; those extra
        bars are trimmed back to the requested window.
        """
        contract = self._expired_future_contract(bar_type.instrument_id)
        instrument_kwargs = (
            {"contracts": [contract]}
            if contract is not None
            else {"instrument_ids": [bar_type.instrument_id.value]}
        )
        return self._request(
            f"historical bars {bar_type}",
            lambda session: self._request_bars_once(
                session,
                bar_type=bar_type,
                start=start,
                end=end,
                instrument_kwargs=instrument_kwargs,
            ),
        )

    async def _request_bars_once(
        self,
        session: Any,
        *,
        bar_type: BarType,
        start: pd.Timestamp,
        end: pd.Timestamp,
        instrument_kwargs: Mapping[str, Any],
    ) -> ProviderAnswer[Bar]:
        # The session turns its own timeout into an empty response. Keep that fallback
        # strictly later so Aegis can preserve the provider failure as an exception.
        request_deadline = min(float(self.timeout), self.call_deadline)
        session_timeout = int(max(float(self.timeout), self.call_deadline)) + 1
        pulled = await asyncio.wait_for(
            session.request_bars(
                bar_specifications=[str(bar_type.spec)],
                end_date_time=_naive_utc(end),
                duration=_ib_duration(start, end),
                tz_name="UTC",
                use_rth=self.use_rth,
                timeout=session_timeout,
                **instrument_kwargs,
            ),
            timeout=request_deadline,
        )
        # The whole-unit duration can reach before `start`; keep only the window.
        bars = [bar for bar in (pulled or []) if bar.ts_event >= start.value]
        # Coverage is served from `start` when history reaches it (contiguous with any
        # prior file), else from the oldest bar IB clamped at (#75, the unclaimed head).
        oldest_verified = (
            start if _history_reached(bars, start) else _first_bar_instant(bars, end)
        )
        return ProviderAnswer.verified(bars, oldest_verified=oldest_verified)

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
        """The daily IBKR ``ADJUSTED_LAST`` close series.

        Nautilus' historic bar path cannot express IBKR's ``ADJUSTED_LAST``
        ``whatToShow`` value, so the historic-session adapter adds that one request
        shape to Nautilus' existing connection, request registry, and callbacks.
        The existing instrument path qualifies the requested identity first; the
        same session submits that complete IB contract without reconstructing it.
        """
        subject = f"ADJUSTED_LAST closes {instrument_id.value}"
        rows = self._request(
            subject,
            lambda session: asyncio.wait_for(
                session.request_adjusted_last(
                    instrument_id=instrument_id,
                    start=start,
                    end=end,
                    expected_currency=currency,
                    deadline=self.call_deadline,
                    timeout=self.timeout,
                    use_rth=self.use_rth,
                ),
                timeout=self.call_deadline,
            ),
        )
        if not rows:
            return pd.Series(dtype=float)
        index = pd.DatetimeIndex([timestamp for timestamp, _close in rows])
        return pd.Series(
            [close for _timestamp, close in rows], index=index
        ).sort_index()

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


# The oldest returned bar within this of the requested start reads as history
# reaching the start across a market closure; a wider gap reads as IB clamping at a
# later listing date (#75).  Wider than any weekend/holiday and far narrower than a
# real listing gap — the only blur is a start authored within this margin of an
# unknown listing, a bounded (<= margin) over-claim the coverage gate tolerates.
_WALL_PROBE_MARGIN = pd.Timedelta(days=14)


def _history_reached(bars: Sequence[Bar], start: pd.Timestamp) -> bool:
    """Whether the answer's oldest bar is close enough to *start* that history covers
    it — only a market closure lies between.  A wider gap is IB clamping at a later
    listing date (#75): the oldest bar is where history begins, not *start*."""
    if not bars:
        return False
    return bars[0].ts_event - start.value <= _WALL_PROBE_MARGIN.value


def _first_bar_instant(bars: Sequence[Bar], fallback: pd.Timestamp) -> pd.Timestamp:
    """Where served history begins: the oldest pulled bar's event time, or
    *fallback* when nothing was pulled at all (nothing is claimed either way)."""
    if not bars:
        return fallback
    return pd.Timestamp(bars[0].ts_event, tz="UTC")


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


async def _request_qualified_contract(
    session: Any,
    instrument_id: InstrumentId,
    *,
    expected_currency: str,
    deadline: float,
) -> IBContract:
    instruments = await _request_instrument_parts(
        session,
        [instrument_id.value],
        [],
        deadline=deadline,
    )
    return _qualified_contract_from_instruments(
        instruments,
        instrument_id,
        expected_currency=expected_currency,
    )


def _qualified_contract_from_instruments(
    instruments: Sequence[Instrument],
    instrument_id: InstrumentId,
    *,
    expected_currency: str,
) -> IBContract:
    from nautilus_trader.adapters.interactive_brokers.common import IBContract

    if len(instruments) != 1:
        raise _QualificationCardinalityError(
            f"expected one qualified instrument for {instrument_id.value}, "
            f"received {len(instruments)}"
        )
    instrument = instruments[0]
    if instrument.id != instrument_id:
        raise _QualificationIdentityError(
            f"qualified instrument identity {instrument.id} does not match "
            f"{instrument_id.value}"
        )
    info = instrument.info
    if not isinstance(info, Mapping) or not isinstance(info.get("contract"), Mapping):
        raise _QualificationMetadataError(
            f"qualified instrument {instrument_id.value} has no IB contract"
        )
    try:
        contract = IBContract(**dict(info["contract"]))
    except (TypeError, ValueError) as exc:
        raise _QualificationMetadataError(
            f"qualified instrument {instrument_id.value} has malformed IB contract: {exc}"
        ) from exc
    if contract.conId <= 0:
        raise _QualificationConIdError(
            f"qualified instrument {instrument_id.value} has no positive IB conId"
        )
    if contract.currency.upper() != expected_currency.upper():
        raise _QualificationCurrencyError(
            f"qualified instrument {instrument_id.value} currency {contract.currency!r} "
            f"does not match requested {expected_currency!r}"
        )
    return contract


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

    The historic client has no teardown or public ``ADJUSTED_LAST`` request.  This
    adapter supplies both while preserving its connection lifecycle, request IDs,
    registry, callbacks, cancellation, and bar decoding.  Isolating those private
    upstream reaches here keeps the provider on a clean session interface.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        # Composition-root reach into Nautilus' missing public historic-session
        # interface.  Every request method talks only to this owned collaborator.
        self._native_client = client._client
        self._await_vendor_request = self._native_client._await_request
        self._native_client._await_request = self._await_request_preserving_failure

    async def connect(self) -> None:
        await self._client.connect()

    async def request_bars(self, **kwargs: Any) -> Sequence[Bar]:
        token = _PRESERVE_HISTORICAL_FAILURE.set(True)
        try:
            return await self._client.request_bars(**kwargs)
        finally:
            _PRESERVE_HISTORICAL_FAILURE.reset(token)

    async def _await_request_preserving_failure(
        self,
        request: Any,
        timeout: int,
        default_value: Any | None = None,
        suppress_timeout_warning: bool = False,
        raise_on_error: bool = False,
    ) -> Any:
        """Tell a failed historical request apart from a genuinely empty one.

        A bar request asks for an empty list as its default, so a fetch that
        timed out and a window that is genuinely empty come back identical —
        and recording the first as verified-empty would durably claim history
        that was never checked.

        ``raise_on_error`` is the vendor's own answer, added in 1.231.0: it
        re-raises the timeout or connection error instead of returning the
        default. Those are the only two paths that return it, so forcing the
        flag inside a historical scope is exactly the distinction needed. This
        override exists solely to inject it, because ``request_bars`` offers no
        way to pass it down; when the vendor wires it into the bar path itself,
        the whole session collaborator can go.
        """
        preserve_failure = (
            _PRESERVE_HISTORICAL_FAILURE.get()
            and isinstance(default_value, list)
            and not default_value
        )
        return await self._await_vendor_request(
            request,
            timeout,
            default_value=default_value,
            suppress_timeout_warning=suppress_timeout_warning,
            raise_on_error=raise_on_error or preserve_failure,
        )

    async def request_instruments(self, **kwargs: Any) -> Sequence[Instrument]:
        return await self._client.request_instruments(**kwargs)

    async def request_adjusted_last(
        self,
        *,
        instrument_id: InstrumentId,
        start: pd.Timestamp,
        end: pd.Timestamp,
        expected_currency: str,
        deadline: float,
        timeout: int,
        use_rth: bool,
    ) -> list[tuple[pd.Timestamp, float]]:
        contract = await _request_qualified_contract(
            self,
            instrument_id,
            expected_currency=expected_currency,
            deadline=deadline,
        )
        bars = await _request_native_adjusted_last(
            self._native_client,
            bar_type=raw_bar_type(instrument_id, "1D"),
            contract=contract,
            duration=_adjusted_last_duration(start, end),
            timeout=timeout,
            use_rth=use_rth,
        )
        return _bounded_adjusted_closes(bars, start=start, end=end)

    async def aclose(self) -> None:
        # The historic client has no public teardown; stopping the inner client
        # drains its background tasks cleanly (so closing the loop is quiet).
        await self._native_client._stop_async()


async def _request_native_adjusted_last(
    client: Any,
    *,
    bar_type: BarType,
    contract: IBContract,
    duration: str,
    timeout: int,
    use_rth: bool,
) -> Sequence[Bar]:
    request = _register_native_adjusted_last(
        client,
        bar_type=bar_type,
        contract=contract,
        duration=duration,
        use_rth=use_rth,
    )
    request.handle()
    bars = await client._await_request(request, timeout)
    if bars is None:
        raise _AdjustedLastCompletionError(
            f"Nautilus did not complete {_ADJUSTED_LAST_WHAT_TO_SHOW} "
            f"request {request.req_id}"
        )
    return bars


def _register_native_adjusted_last(
    client: Any,
    *,
    bar_type: BarType,
    contract: IBContract,
    duration: str,
    use_rth: bool,
) -> Any:
    from nautilus_trader.adapters.interactive_brokers.parsing.data import (
        bar_spec_to_bar_size,
    )

    req_id = client._next_req_id()
    request = client._requests.add(
        req_id=req_id,
        name=(str(bar_type), _ADJUSTED_LAST_WHAT_TO_SHOW, duration),
        handle=functools.partial(
            client._eclient.reqHistoricalData,
            reqId=req_id,
            contract=contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_spec_to_bar_size(bar_type.spec),
            whatToShow=_ADJUSTED_LAST_WHAT_TO_SHOW,
            useRTH=use_rth,
            formatDate=2,
            keepUpToDate=False,
            chartOptions=[],
        ),
        cancel=functools.partial(
            client._eclient.cancelHistoricalData,
            reqId=req_id,
        ),
    )
    if request is None:
        raise _AdjustedLastRegistrationError(
            f"Nautilus did not register {_ADJUSTED_LAST_WHAT_TO_SHOW} request {req_id}"
        )
    return request


def _ib_duration(start: pd.Timestamp, end: pd.Timestamp) -> str:
    days = max(1, math.ceil((_utc(end) - _utc(start)) / pd.Timedelta(days=1)))
    if days <= 365:
        return f"{days} D"
    return f"{math.ceil(days / 365)} Y"


def _adjusted_last_duration(start: pd.Timestamp, end: pd.Timestamp) -> str:
    return _ib_duration(start, max(_utc(end), pd.Timestamp.now(tz="UTC")))


def _bounded_adjusted_closes(
    bars: Sequence[Bar],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[tuple[pd.Timestamp, float]]:
    start_ts = _utc(start)
    end_ts = _utc(end)
    bounded: list[tuple[pd.Timestamp, float]] = []
    for bar in bars:
        timestamp = pd.Timestamp(bar.ts_event, unit="ns", tz="UTC")
        if start_ts <= timestamp <= end_ts:
            bounded.append((timestamp, bar.close.as_double()))
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
    catalog: Catalog,
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
        catalog.store_definitions(
            [_catalog_safe_instrument(instrument) for instrument in instruments]
        )


def _missing_definitions(
    catalog: Catalog, instrument_ids: Sequence[InstrumentId]
) -> list[InstrumentId]:
    present = {instrument.id for instrument in catalog.definitions(instrument_ids)}
    return [
        instrument_id
        for instrument_id in instrument_ids
        if instrument_id not in present
    ]


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
