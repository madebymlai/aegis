"""Provider-neutral storage and ingestion of typed adjacent market data.

The interface deals only in domain records, provider ports, instruments, time
windows, and a catalog root. Nautilus interval and serialization machinery is
kept inside this module.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

import pandas as pd
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.config import DataEngineConfig
from nautilus_trader.core.data import Data
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.client import DataClient
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.data.messages import RequestData
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.model.data import DataType
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId

from aegis_data import custom_kinds
from aegis_data.custom_kinds import CustomDataKind, CustomDataRegistry
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_data.provider_errors import gap_fill_boundary


RecordT = TypeVar("RecordT", bound=Data)
ProviderRecordT = TypeVar("ProviderRecordT", bound=Data, covariant=True)


class CustomDataProviderPort(Protocol[ProviderRecordT]):
    """Pure fetch seam for one typed custom-data need."""

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> Sequence[ProviderRecordT]: ...


type CustomArrayRequirements = Mapping[InstrumentId, Sequence[str]]
type CustomDataProviderMap = Mapping[type[Data], CustomDataProviderPort[Any]]
type CustomDataAdapterMap = Mapping[type[Data], object]
type CustomDataClientFactory = Callable[
    [MessageBus, Cache, TestClock, list[Exception]],
    DataClient,
]

_CUSTOM_DATA_CLIENT_ID = ClientId("AEGIS-CUSTOM-HIST")
_CUSTOM_DATA_TRADER_ID = TraderId("AEGIS-CUSTOM-001")


class InvalidLiveCustomDataCapabilityError(TypeError):
    """Raised when a provider describes an invalid live-data capability."""


class InvalidLiveDataClientNameError(ValueError):
    """Raised when a live custom-data client name is empty."""


@dataclass(frozen=True)
class LiveDataClientName:
    """Provider-neutral name for one live custom-data client."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidLiveDataClientNameError(
                "live data client name must not be empty"
            )


@dataclass(frozen=True)
class LiveCustomDataCapability:
    """The native Nautilus capability exposed by a streaming provider."""

    client_name: LiveDataClientName
    config: LiveDataClientConfig
    factory: type[LiveDataClientFactory]

    def __post_init__(self) -> None:
        valid = (
            isinstance(self.client_name, LiveDataClientName)
            and isinstance(self.config, LiveDataClientConfig)
            and isinstance(self.factory, type)
            and issubclass(self.factory, LiveDataClientFactory)
        )
        if not valid:
            raise InvalidLiveCustomDataCapabilityError(
                "live custom-data capability requires a client name, live client config, "
                "and factory"
            )


class UnknownCustomDataRecordError(ValueError):
    """The requested domain record has no Custom Data implementation."""


class UnknownCustomArrayError(ValueError):
    """One or more requested arrays have no Custom Data implementation."""

    def __init__(self, array_names: Sequence[str]) -> None:
        self.array_names = tuple(array_names)
        super().__init__(f"unknown custom arrays: {list(self.array_names)}")


class CustomDataRequestCompletionError(RuntimeError):
    """Nautilus did not complete a synchronous Custom Data request."""


class _ProviderBackedCustomDataClient(DataClient):
    """Translate Nautilus Custom Data requests through configured provider ports."""

    def __init__(
        self,
        msgbus: MessageBus,
        cache: Cache,
        clock: TestClock,
        providers: CustomDataProviderMap,
        failures: list[Exception],
    ) -> None:
        super().__init__(_CUSTOM_DATA_CLIENT_ID, msgbus, cache, clock, None)
        self._providers = providers
        self._failures = failures

    def _connect(self) -> None:
        pass

    def _disconnect(self) -> None:
        pass

    def request(self, request: RequestData) -> None:
        record_type = cast(type[Data], request.data_type.type)
        instrument_id = cast(InstrumentId, request.instrument_id)
        interval = CatalogInterval(request.start.value, request.end.value)
        provider = self._providers[record_type]
        try:
            records = _provider_records(
                provider,
                record_type=record_type,
                instrument_id=instrument_id,
                interval=interval,
            )
        except Exception as error:
            self._failures.append(error)
            records = ()
        self._handle_data_response_py(
            request.data_type,
            list(records),
            request.id,
            request.start,
            request.end,
            request.params,
        )


@dataclass(frozen=True)
class CustomDataWarmer:
    """Warm provider-backed Custom Data through Nautilus's native request path."""

    catalog: Catalog
    client_factory: CustomDataClientFactory | None

    def warm(
        self,
        record_type: type[Data],
        instrument_ids: Sequence[InstrumentId],
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        params: dict[str, Any] | None = None,
    ) -> None:
        start = _utc(start)
        end = _utc(end)
        if start > end:
            raise ValueError("custom data warm start must not be after end")
        interval = CatalogInterval(start.value, end.value)
        for instrument_id in instrument_ids:
            self._warm_instrument(
                record_type,
                instrument_id,
                interval,
                params=params,
            )

    def _warm_instrument(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CatalogInterval,
        *,
        params: dict[str, Any] | None,
    ) -> None:
        clock = TestClock()
        clock.set_time(interval.end_ns + 1)
        msgbus = MessageBus(trader_id=_CUSTOM_DATA_TRADER_ID, clock=clock)
        cache = Cache()
        engine = DataEngine(msgbus, cache, clock, DataEngineConfig())
        self.catalog.register_with(engine)
        failures: list[Exception] = []
        if self.client_factory is not None:
            engine.register_default_client(
                self.client_factory(msgbus, cache, clock, failures)
            )
        engine.start()
        completed: list[object] = []
        request = RequestData(
            data_type=DataType(record_type),
            instrument_id=instrument_id,
            start=interval.start,
            end=interval.end,
            limit=0,
            client_id=None,
            venue=instrument_id.venue,
            callback=completed.append,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params={**(params or {}), "update_catalog": True},
        )
        try:
            msgbus.request(endpoint="DataEngine.request", request=request)
        finally:
            engine.stop()
        if failures:
            with gap_fill_boundary(f"custom data for {instrument_id.value}"):
                raise failures[0]
        if not completed:
            raise CustomDataRequestCompletionError(
                f"Nautilus did not complete Custom Data request for "
                f"{record_type.__name__} and {instrument_id.value}"
            )


def ensure_arrays(
    requirements: CustomArrayRequirements,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: CustomDataProviderMap,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Ensure catalog coverage for every kind behind the requested arrays."""
    instrument_ids_by_record_type: dict[type[Data], dict[InstrumentId, None]] = {}
    for instrument_id, array_names in requirements.items():
        for kind in _kinds_for_array_names(array_names, registry):
            instrument_ids_by_record_type.setdefault(kind.record_type, {})[
                instrument_id
            ] = None
    for record_type, instrument_ids in instrument_ids_by_record_type.items():
        provider = providers.get(record_type)
        client_factory = (
            None
            if provider is None
            else provider_backed_custom_data_client_factory({record_type: provider})
        )
        warmer = CustomDataWarmer(catalog, client_factory)
        warmer.warm(
            record_type,
            tuple(instrument_ids),
            start=start,
            end=end,
        )


def provider_backed_custom_data_client_factory(
    providers: CustomDataProviderMap,
) -> CustomDataClientFactory:
    """Adapt configured provider ports to Nautilus's historical client seam."""

    def build(
        msgbus: MessageBus,
        cache: Cache,
        clock: TestClock,
        failures: list[Exception],
    ) -> DataClient:
        return _ProviderBackedCustomDataClient(
            msgbus,
            cache,
            clock,
            providers,
            failures,
        )

    return build


def _provider_records(
    provider: CustomDataProviderPort[RecordT],
    *,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    interval: CatalogInterval,
) -> tuple[RecordT, ...]:
    served = provider.request_records(
        instrument_id,
        start=interval.start,
        end=interval.end,
    )
    records = tuple(
        sorted(
            (
                _validate_record(
                    record,
                    record_type=record_type,
                    instrument_id=instrument_id,
                )
                for record in served
            ),
            key=lambda record: record.ts_event,
        )
    )
    outside = tuple(
        record
        for record in records
        if not interval.start_ns <= record.ts_event <= interval.end_ns
    )
    if outside:
        raise ValueError(
            "provider returned a custom-data record outside the requested window"
        )
    return records


def capture(
    record: RecordT,
    *,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Persist one observed record over the single instant it covers.

    An observation answers for its own timestamp and nothing either side of it,
    so the window written is the instant itself. Validation happens here, before
    the write, so the Catalog is only ever handed records that belong to it.
    """
    record_type = type(record)
    _kind_for(record_type, registry)
    instrument_id = cast(InstrumentId, record.instrument_id)
    _validate_record(
        record,
        record_type=record_type,
        instrument_id=instrument_id,
    )
    catalog.replace(
        CatalogKey.for_instrument(record_type, instrument_id),
        CatalogInterval(record.ts_event, record.ts_event),
        (record,),
    )


def correct(
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    replacement: Sequence[RecordT],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Deliberately replace one bounded window, including verified emptiness."""
    _kind_for(record_type, registry)
    start = _utc(start)
    end = _utc(end)
    interval = CatalogInterval(start.value, end.value)
    subject = CatalogKey.for_instrument(record_type, instrument_id)
    selected = tuple(
        record
        for record in replacement
        if _record_belongs_to_interval(
            record,
            record_type=record_type,
            instrument_id=instrument_id,
            start=start,
            end=end,
        )
    )
    catalog.replace(subject, interval, selected)
    catalog.compact(subject, interval)


def arrays(
    array_names: Sequence[str],
    instrument_ids: Sequence[InstrumentId],
    *,
    index: pd.DatetimeIndex,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> dict[str, pd.DataFrame]:
    """Project the latest causally known record onto the caller's exact index."""
    kinds = _kinds_for_array_names(array_names, registry)
    if len(index) == 0:
        return {
            name: pd.DataFrame(index=index, columns=instrument_ids, dtype=float)
            for name in array_names
        }
    panels = {
        name: pd.DataFrame(0.0, index=index, columns=instrument_ids)
        for name in array_names
    }
    for kind in kinds:
        stored = _query_records(
            kind.record_type,
            instrument_ids,
            start=None,
            end=pd.Timestamp(index[-1]),
            catalog=catalog,
        )
        _project_records(kind, stored, instrument_ids, index, panels)
    return panels


def records_for_arrays(
    required_arrays: Mapping[InstrumentId, Sequence[str]],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> tuple[Data, ...]:
    """Return only the catalog records that back requested value arrays."""
    array_names = tuple(
        dict.fromkeys(name for names in required_arrays.values() for name in names)
    )
    selected: list[Data] = []
    for kind in _kinds_for_array_names(array_names, registry):
        instrument_ids = tuple(
            instrument_id
            for instrument_id, names in required_arrays.items()
            if set(names).intersection(kind.array_names)
        )
        selected.extend(
            records(
                kind.record_type,
                instrument_ids,
                start=start,
                end=end,
                catalog=catalog,
                registry=registry,
            )
        )
    return tuple(selected)


def records(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> tuple[RecordT, ...]:
    """Read typed domain records for an instrument window."""
    _kind_for(record_type, registry)
    return _query_records(
        record_type,
        instrument_ids,
        start=start,
        end=end,
        catalog=catalog,
    )


def _query_records(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp,
    catalog: Catalog,
) -> tuple[RecordT, ...]:
    stored: list[RecordT] = []
    for instrument_id in instrument_ids:
        queried = catalog.read_all(
            CatalogKey.for_instrument(record_type, instrument_id)
        )
        start_ns = _utc(start).value if start is not None else None
        end_ns = _utc(end).value
        stored.extend(
            item
            for item in queried
            if (start_ns is None or item.ts_event >= start_ns)
            and item.ts_event <= end_ns
        )
    return tuple(
        sorted(
            stored,
            key=lambda item: (
                cast(InstrumentId, item.instrument_id).value,
                item.ts_event,
            ),
        )
    )


def _validate_record(
    record: RecordT,
    *,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
) -> RecordT:
    if not isinstance(record, record_type):
        raise TypeError(
            f"provider returned {type(record).__name__}, expected {record_type.__name__}"
        )
    if cast(InstrumentId, record.instrument_id) != instrument_id:
        raise ValueError(
            "provider returned a custom-data record for another instrument"
        )
    return record


def _record_belongs_to_interval(
    record: RecordT,
    *,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> bool:
    _validate_record(
        record,
        record_type=record_type,
        instrument_id=instrument_id,
    )
    return start.value <= record.ts_event <= end.value


def _registry(registry: CustomDataRegistry | None) -> CustomDataRegistry:
    return (
        registry if registry is not None else custom_kinds.declared_custom_data_kinds()
    )


def _kind_for(
    record_type: type[Data],
    registry: CustomDataRegistry | None,
) -> CustomDataKind:
    try:
        return _registry(registry).kind_for(record_type)
    except KeyError:
        raise UnknownCustomDataRecordError(record_type.__name__) from None


def _kinds_for_array_names(
    array_names: Sequence[str],
    registry: CustomDataRegistry | None,
) -> tuple[CustomDataKind, ...]:
    try:
        return _registry(registry).kinds_for_arrays(array_names)
    except KeyError as error:
        raise UnknownCustomArrayError(cast(tuple[str, ...], error.args[0])) from None


def _project_records(
    kind: CustomDataKind,
    stored: Sequence[Data],
    instrument_ids: Sequence[InstrumentId],
    index: pd.DatetimeIndex,
    panels: dict[str, pd.DataFrame],
) -> None:
    projection = kind.projection
    for instrument_id in instrument_ids:
        instrument_records = sorted(
            (
                record
                for record in stored
                if cast(InstrumentId, record.instrument_id) == instrument_id
            ),
            key=lambda record: (record.ts_event, record.ts_init),
        )
        cursor = 0
        current: Data | None = None
        for row in index:
            row_ns = _utc(pd.Timestamp(row)).value
            while (
                cursor < len(instrument_records)
                and instrument_records[cursor].ts_event <= row_ns
            ):
                current = instrument_records[cursor]
                cursor += 1
            if current is None:
                continue
            if projection.value_array in panels:
                panels[projection.value_array].at[row, instrument_id] = float(
                    getattr(current, projection.value_attribute)
                )
            if projection.availability_array in panels:
                panels[projection.availability_array].at[row, instrument_id] = 1.0
            if projection.age_array in panels:
                panels[projection.age_array].at[row, instrument_id] = (
                    row_ns - current.ts_event
                ) / 86_400_000_000_000


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


__all__ = [
    "CustomArrayRequirements",
    "CustomDataAdapterMap",
    "CustomDataClientFactory",
    "CustomDataProviderMap",
    "CustomDataProviderPort",
    "InvalidLiveCustomDataCapabilityError",
    "InvalidLiveDataClientNameError",
    "LiveCustomDataCapability",
    "LiveDataClientName",
    "UnknownCustomArrayError",
    "UnknownCustomDataRecordError",
    "CustomDataRequestCompletionError",
    "CustomDataWarmer",
    "arrays",
    "capture",
    "correct",
    "ensure_arrays",
    "records",
    "records_for_arrays",
    "provider_backed_custom_data_client_factory",
]
