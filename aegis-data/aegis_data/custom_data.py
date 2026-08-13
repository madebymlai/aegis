"""Provider-neutral storage and ingestion of typed adjacent market data.

The interface deals only in domain records, provider ports, instruments, time
windows, and a catalog root. Nautilus interval and serialization machinery is
kept inside this module.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import time_ns
from typing import Any, Callable, Protocol, TypeVar, cast

import pandas as pd
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.core.data import Data
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import (
    CoverageInterval,
    ensure_coverage,
)
from aegis_data import custom_kinds
from aegis_data.custom_kinds import CustomDataKind, CustomDataRegistry
from aegis_data.raw_bars import CatalogCoverageGapError, gap_fill_boundary
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_data.provider import ProviderAnswer


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
    ) -> ProviderAnswer[ProviderRecordT]: ...


type CustomArrayRequirements = Mapping[InstrumentId, Sequence[str]]
type CustomDataProviderMap = Mapping[type[Data], CustomDataProviderPort[Any]]
type CustomDataAdapterMap = Mapping[type[Data], object]


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


@dataclass(frozen=True)
class CustomDataCoverage:
    """Coverage provenance for one requested instrument window."""

    instrument_id: InstrumentId
    checked_at_ns: int | None


def ingest(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    provider: CustomDataProviderPort[RecordT] | None,
    catalog: Catalog,
    clock_ns: Callable[[], int] = time_ns,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Fill only catalog-native missing intervals through the declared provider."""
    _kind_for(record_type, registry)
    start = _utc(start)
    end = _utc(end)
    if start > end:
        raise ValueError("custom data ingest start must not be after end")
    for instrument_id in instrument_ids:
        _ensure_instrument_coverage(
            catalog=catalog,
            record_type=record_type,
            instrument_id=instrument_id,
            start=start,
            end=end,
            provider=provider,
            clock_ns=clock_ns,
        )


def ensure_arrays(
    requirements: CustomArrayRequirements,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: CustomDataProviderMap,
    catalog: Catalog,
    clock_ns: Callable[[], int] = time_ns,
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
        ingest(
            record_type,
            tuple(instrument_ids),
            start=start,
            end=end,
            provider=providers.get(record_type),
            catalog=catalog,
            clock_ns=clock_ns,
            registry=registry,
        )


def _ensure_instrument_coverage(
    *,
    catalog: Catalog,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
    provider: CustomDataProviderPort[RecordT] | None,
    clock_ns: Callable[[], int],
) -> None:
    requested = CoverageInterval(start.value, end.value)
    markers = CoverageMarkerLedger(catalog)
    subject = CatalogKey.for_instrument(record_type, instrument_id)

    def commit(
        verified: CoverageInterval,
        verified_records: tuple[RecordT, ...],
    ) -> None:
        catalog.replace(
            subject,
            CatalogInterval(verified.start_ns, verified.end_ns),
            verified_records,
        )
        markers.mark(
            subject,
            verified,
            checked_at_ns=clock_ns(),
            applicable=True,
        )

    ensure_coverage(
        subject=f"custom data for {instrument_id.value}",
        provider=(
            _record_fetcher(provider, instrument_id, record_type)
            if provider is not None
            else None
        ),
        missing_intervals=lambda: markers.missing(subject, requested),
        coverage_error=lambda missing: _coverage_gap(
            subject,
            instrument_id,
            missing,
        ),
        provider_boundary=gap_fill_boundary,
        commit=commit,
        finalize=lambda: markers.consolidate(subject, requested),
        select_records=_records_within_event_window,
    )


def capture(
    record: RecordT,
    *,
    catalog: Catalog,
    clock_ns: Callable[[], int] = time_ns,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Persist one observed record and its point coverage."""
    record_type = type(record)
    _kind_for(record_type, registry)
    instrument_id = cast(InstrumentId, record.instrument_id)
    _validate_record(
        record,
        record_type=record_type,
        instrument_id=instrument_id,
    )
    markers = CoverageMarkerLedger(catalog)
    subject = CatalogKey.for_instrument(record_type, instrument_id)
    catalog.replace(
        subject,
        CatalogInterval(record.ts_event, record.ts_event),
        (record,),
    )
    point = CoverageInterval(record.ts_event, record.ts_event)
    markers.mark(
        subject,
        point,
        checked_at_ns=clock_ns(),
        applicable=True,
    )


def correct(
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    replacement: Sequence[RecordT],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog: Catalog,
    clock_ns: Callable[[], int] = time_ns,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Deliberately replace one bounded window, including verified emptiness."""
    _kind_for(record_type, registry)
    start = _utc(start)
    end = _utc(end)
    markers = CoverageMarkerLedger(catalog)
    interval = CoverageInterval(start.value, end.value)
    subject = CatalogKey.for_instrument(record_type, instrument_id)
    markers.delete(subject, interval)
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
    catalog.replace(
        subject,
        CatalogInterval(start.value, end.value),
        selected,
    )
    markers.mark(
        subject,
        interval,
        checked_at_ns=clock_ns(),
        applicable=True,
    )
    markers.consolidate(subject, interval)


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
        coverage(
            cast(type[Data], kind.record_type),
            instrument_ids,
            start=pd.Timestamp(index[0]),
            end=pd.Timestamp(index[-1]),
            catalog=catalog,
            registry=registry,
        )
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
        coverage(
            cast(type[Data], kind.record_type),
            instrument_ids,
            start=start,
            end=end,
            catalog=catalog,
            registry=registry,
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


def coverage(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> tuple[CustomDataCoverage, ...]:
    """Prove requested coverage and report checked-at marker provenance."""
    _kind_for(record_type, registry)
    markers = CoverageMarkerLedger(catalog)
    start = _utc(start)
    end = _utc(end)
    reports: list[CustomDataCoverage] = []
    for instrument_id in instrument_ids:
        interval = CoverageInterval(start.value, end.value)
        subject = CatalogKey.for_instrument(record_type, instrument_id)
        missing = tuple(markers.missing(subject, interval))
        if missing:
            raise _coverage_gap(subject, instrument_id, missing)
        checked_at = markers.checked_at_values(
            subject,
            interval,
        )
        reports.append(
            CustomDataCoverage(
                instrument_id=instrument_id,
                checked_at_ns=max(checked_at, default=None),
            )
        )
    return tuple(reports)


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


def _record_fetcher(
    provider: CustomDataProviderPort[RecordT],
    instrument_id: InstrumentId,
    record_type: type[RecordT],
) -> Callable[[pd.Timestamp, pd.Timestamp], ProviderAnswer[RecordT]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> ProviderAnswer[RecordT]:
        served = provider.request_records(instrument_id, start=start, end=end)
        selected = tuple(
            sorted(
                (
                    _validate_record(
                        record,
                        record_type=record_type,
                        instrument_id=instrument_id,
                    )
                    for record in served.records
                ),
                key=lambda record: record.ts_event,
            )
        )
        return ProviderAnswer.verified(
            selected,
            oldest_verified=_utc(served.oldest_verified),
        )

    return fetch


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


def _records_within_event_window(
    stored: Sequence[RecordT], interval: CoverageInterval
) -> tuple[RecordT, ...]:
    return tuple(
        record
        for record in stored
        if interval.start_ns <= record.ts_event <= interval.end_ns
    )


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
    return registry if registry is not None else custom_kinds.declared_custom_data_kinds()


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


def _coverage_gap(
    subject: CatalogKey[RecordT],
    instrument_id: InstrumentId,
    missing: Sequence[CoverageInterval],
) -> CatalogCoverageGapError:
    intervals = tuple(missing)
    return CatalogCoverageGapError(
        subject,
        intervals,
        message=(
            f"custom data coverage is missing for {instrument_id.value}: "
            f"{[(item.start_ns, item.end_ns) for item in intervals]}"
        ),
    )


__all__ = [
    "CustomArrayRequirements",
    "CustomDataCoverage",
    "CustomDataAdapterMap",
    "CustomDataProviderMap",
    "CustomDataProviderPort",
    "InvalidLiveCustomDataCapabilityError",
    "InvalidLiveDataClientNameError",
    "LiveCustomDataCapability",
    "LiveDataClientName",
    "UnknownCustomArrayError",
    "UnknownCustomDataRecordError",
    "arrays",
    "capture",
    "correct",
    "coverage",
    "ensure_arrays",
    "ingest",
    "records",
    "records_for_arrays",
]
