"""Provider-neutral storage and ingestion of typed adjacent market data.

The interface deals only in domain records, provider ports, instruments, time
windows, and a catalog root. Nautilus interval and serialization machinery is
kept inside this module.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import time_ns
from typing import Any, Callable, Generic, Protocol, TypeVar, cast

import pandas as pd
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.core.data import Data
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import (
    CoverageInterval,
    ServedRecords,
    ensure_coverage,
)
from aegis_data.catalog import gap_fill_boundary


@customdataclass
class FixtureRecord(Data):
    """Test-owned typed record used to prove the generic module."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    value: float = 0.0
    provider: str = "fixture"


@customdataclass
class _DormantFixtureRecord(Data):
    """Known fixture shape with deliberately absent provider wiring."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    value: float = 0.0


RecordT = TypeVar("RecordT", bound=Data)


@dataclass(frozen=True)
class ServedCustomData(Generic[RecordT]):
    """A provider answer plus the oldest instant it verified."""

    records: tuple[RecordT, ...]
    served_from: pd.Timestamp


class CustomDataProviderPort(Protocol[RecordT]):
    """Pure fetch seam for one typed custom-data need."""

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[RecordT]: ...


type CustomArrayRequirements = Mapping[InstrumentId, Sequence[str]]
type CustomDataProviderMap = Mapping[type[Data], Sequence[CustomDataProviderPort[Any]]]


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
    record_types: tuple[type[Data], ...]

    def __post_init__(self) -> None:
        valid = (
            isinstance(self.client_name, LiveDataClientName)
            and isinstance(self.config, LiveDataClientConfig)
            and isinstance(self.factory, type)
            and issubclass(self.factory, LiveDataClientFactory)
            and bool(self.record_types)
            and all(
                isinstance(record_type, type) and issubclass(record_type, Data)
                for record_type in self.record_types
            )
        )
        if not valid:
            raise InvalidLiveCustomDataCapabilityError(
                "live custom-data capability requires a client name, live client config, "
                "factory, and at least one Data record type"
            )


@dataclass(frozen=True)
class _ArrayProjection:
    value_array: str
    availability_array: str
    age_array: str
    value_attribute: str

    @property
    def array_names(self) -> tuple[str, ...]:
        return (self.value_array, self.availability_array, self.age_array)


@dataclass(frozen=True)
class _ArrayKind:
    record_type: type[Data]
    projection: _ArrayProjection
    provisioned: bool

    @property
    def array_names(self) -> tuple[str, ...]:
        return self.projection.array_names


_KINDS: tuple[_ArrayKind, ...] = (
    _ArrayKind(
        record_type=FixtureRecord,
        provisioned=True,
        projection=_ArrayProjection(
            value_array="FixtureValue",
            availability_array="FixtureAvailable",
            age_array="FixtureAgeDays",
            value_attribute="value",
        ),
    ),
    _ArrayKind(
        record_type=_DormantFixtureRecord,
        provisioned=False,
        projection=_ArrayProjection(
            value_array="DormantFixtureValue",
            availability_array="DormantFixtureAvailable",
            age_array="DormantFixtureAgeDays",
            value_attribute="value",
        ),
    ),
)

KNOWN_CUSTOM_ARRAY_NAMES = frozenset(
    array_name for kind in _KINDS for array_name in kind.array_names
)
VOCABULARY = frozenset(
    array_name for kind in _KINDS if kind.provisioned for array_name in kind.array_names
)
AVAILABILITY_BY_VALUE = {
    kind.projection.value_array: kind.projection.availability_array
    for kind in _KINDS
}


class UnknownCustomDataRecordError(ValueError):
    """The requested domain record has no Custom Data implementation."""


class UnknownCustomArrayError(ValueError):
    """One or more requested arrays have no Custom Data implementation."""

    def __init__(self, array_names: Sequence[str]) -> None:
        self.array_names = tuple(array_names)
        super().__init__(f"unknown custom arrays: {list(self.array_names)}")


class CustomDataCoverageError(ValueError):
    """A requested custom-data window has never been completely ingested."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        missing: tuple[CoverageInterval, ...],
    ) -> None:
        self.instrument_id = instrument_id
        self.missing = missing
        super().__init__(
            f"custom data coverage is missing for {instrument_id.value}: "
            f"{[(item.start_ns, item.end_ns) for item in missing]}"
        )


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
    providers: Sequence[CustomDataProviderPort[RecordT]],
    catalog_path: Path,
    clock_ns: Callable[[], int] = time_ns,
) -> None:
    """Fill only catalog-native missing intervals, in provider tuple order."""
    _kind_for(record_type)
    start = _utc(start)
    end = _utc(end)
    if start > end:
        raise ValueError("custom data ingest start must not be after end")
    catalog = ParquetDataCatalog(str(catalog_path))
    for instrument_id in instrument_ids:
        _ensure_instrument_coverage(
            catalog=catalog,
            record_type=record_type,
            instrument_id=instrument_id,
            start=start,
            end=end,
            providers=providers,
            clock_ns=clock_ns,
        )


def ensure_arrays(
    requirements: CustomArrayRequirements,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: CustomDataProviderMap,
    catalog_path: Path,
    clock_ns: Callable[[], int] = time_ns,
) -> None:
    """Ensure catalog coverage for every kind behind the requested arrays."""
    instrument_ids_by_record_type: dict[type[Data], dict[InstrumentId, None]] = {}
    for instrument_id, array_names in requirements.items():
        for kind in _kinds_for_array_names(array_names):
            instrument_ids_by_record_type.setdefault(kind.record_type, {})[
                instrument_id
            ] = None
    for record_type, instrument_ids in instrument_ids_by_record_type.items():
        ingest(
            record_type,
            tuple(instrument_ids),
            start=start,
            end=end,
            providers=providers.get(record_type, ()),
            catalog_path=catalog_path,
            clock_ns=clock_ns,
        )


def _ensure_instrument_coverage(
    *,
    catalog: ParquetDataCatalog,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: Sequence[CustomDataProviderPort[RecordT]],
    clock_ns: Callable[[], int],
) -> None:
    requested = CoverageInterval(start.value, end.value)
    markers = CoverageMarkerLedger(catalog)

    def commit(
        verified: CoverageInterval,
        verified_records: tuple[RecordT, ...],
    ) -> None:
        if verified_records:
            catalog.write_data(
                list(verified_records),
                data_cls=record_type,
                identifier=instrument_id.value,
                start=verified.start_ns,
                end=verified.end_ns,
            )
        markers.mark(
            record_type,
            instrument_id,
            verified,
            checked_at_ns=clock_ns(),
            applicable=True,
        )

    ensure_coverage(
        subject=f"custom data for {instrument_id.value}",
        fetchers=tuple(
            _record_fetcher(provider, instrument_id, record_type)
            for provider in providers
        ),
        missing_intervals=lambda: markers.missing(
            record_type, instrument_id, requested
        ),
        coverage_error=lambda missing: CustomDataCoverageError(
            instrument_id, tuple(missing)
        ),
        provider_boundary=gap_fill_boundary,
        commit=commit,
        finalize=lambda: markers.consolidate(
            record_type, instrument_id, requested
        ),
        select_records=_records_within_event_window,
    )


def capture(
    record: RecordT,
    *,
    catalog_path: Path,
    clock_ns: Callable[[], int] = time_ns,
) -> None:
    """Persist one live record at its point-in-time catalog coordinate."""
    record_type = type(record)
    _kind_for(record_type)
    instrument_id = cast(InstrumentId, record.instrument_id)
    _validate_record(
        record,
        record_type=record_type,
        instrument_id=instrument_id,
    )
    catalog = ParquetDataCatalog(str(catalog_path))
    markers = CoverageMarkerLedger(catalog)
    catalog.write_data(
        [record],
        data_cls=record_type,
        identifier=instrument_id.value,
        start=record.ts_event,
        end=record.ts_event,
    )
    point = CoverageInterval(record.ts_event, record.ts_event)
    markers.mark(
        record_type,
        instrument_id,
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
    catalog_path: Path,
    clock_ns: Callable[[], int] = time_ns,
) -> None:
    """Deliberately replace one bounded window, including verified emptiness."""
    _kind_for(record_type)
    start = _utc(start)
    end = _utc(end)
    catalog = ParquetDataCatalog(str(catalog_path))
    markers = CoverageMarkerLedger(catalog)
    interval = CoverageInterval(start.value, end.value)
    catalog.delete_data_range(
        record_type,
        identifier=instrument_id.value,
        start=start,
        end=end,
    )
    markers.delete(record_type, instrument_id, interval)
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
    if selected:
        catalog.write_data(
            list(selected),
            data_cls=record_type,
            identifier=instrument_id.value,
            start=start.value,
            end=end.value,
        )
    markers.mark(
        record_type,
        instrument_id,
        interval,
        checked_at_ns=clock_ns(),
        applicable=True,
    )
    markers.consolidate(record_type, instrument_id, interval)


def arrays(
    array_names: Sequence[str],
    instrument_ids: Sequence[InstrumentId],
    *,
    index: pd.DatetimeIndex,
    catalog_path: Path,
) -> dict[str, pd.DataFrame]:
    """Project the latest causally known record onto the caller's exact index."""
    kinds = _kinds_for_array_names(array_names)
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
            catalog_path=catalog_path,
        )
        stored = _query_records(
            kind.record_type,
            instrument_ids,
            start=None,
            end=pd.Timestamp(index[-1]),
            catalog_path=catalog_path,
        )
        _project_records(kind, stored, instrument_ids, index, panels)
    return panels


def records_for_arrays(
    required_arrays: Mapping[InstrumentId, Sequence[str]],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog_path: Path,
) -> tuple[Data, ...]:
    """Return only the catalog records that back requested value arrays."""
    array_names = tuple(
        dict.fromkeys(name for names in required_arrays.values() for name in names)
    )
    selected: list[Data] = []
    for kind in _kinds_for_array_names(array_names):
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
            catalog_path=catalog_path,
        )
        selected.extend(
            records(
                kind.record_type,
                instrument_ids,
                start=start,
                end=end,
                catalog_path=catalog_path,
            )
        )
    return tuple(selected)


def coverage(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    catalog_path: Path,
) -> tuple[CustomDataCoverage, ...]:
    """Prove requested coverage and report checked-at marker provenance."""
    _kind_for(record_type)
    catalog = ParquetDataCatalog(str(catalog_path))
    markers = CoverageMarkerLedger(catalog)
    start = _utc(start)
    end = _utc(end)
    reports: list[CustomDataCoverage] = []
    for instrument_id in instrument_ids:
        interval = CoverageInterval(start.value, end.value)
        missing = tuple(markers.missing(record_type, instrument_id, interval))
        if missing:
            raise CustomDataCoverageError(instrument_id, missing)
        checked_at = markers.checked_at_values(
            record_type,
            instrument_id,
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
    catalog_path: Path,
) -> tuple[RecordT, ...]:
    """Read typed domain records for an instrument window."""
    _kind_for(record_type)
    return _query_records(
        record_type,
        instrument_ids,
        start=start,
        end=end,
        catalog_path=catalog_path,
    )


def _query_records(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp,
    catalog_path: Path,
) -> tuple[RecordT, ...]:
    catalog = ParquetDataCatalog(str(catalog_path))
    stored: list[RecordT] = []
    for instrument_id in instrument_ids:
        queried = catalog.query(
            record_type,
            identifiers=[instrument_id.value],
            start=_utc(start) if start is not None else None,
            end=_utc(end),
        )
        stored.extend(_as_record(item, record_type) for item in queried)
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
) -> Callable[[pd.Timestamp, pd.Timestamp], ServedRecords[RecordT]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> ServedRecords[RecordT]:
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
        return ServedRecords(selected, _utc(served.served_from))

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


def _kind_for(record_type: type[Data]) -> _ArrayKind:
    for kind in _KINDS:
        if kind.record_type is record_type:
            return kind
    raise UnknownCustomDataRecordError(record_type.__name__)


def _kinds_for_array_names(array_names: Sequence[str]) -> tuple[_ArrayKind, ...]:
    requested = set(array_names)
    kinds = tuple(
        kind
        for kind in _KINDS
        if requested.intersection(kind.array_names)
    )
    resolved = {name for kind in kinds for name in kind.array_names}
    unknown = sorted(requested - resolved)
    if unknown:
        raise UnknownCustomArrayError(unknown)
    return kinds


def _project_records(
    kind: _ArrayKind,
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


def _as_record(item: object, record_type: type[RecordT]) -> RecordT:
    value = item.data if hasattr(item, "data") else item
    if not isinstance(value, record_type):
        raise TypeError(
            f"catalog returned {type(value).__name__}, expected {record_type.__name__}"
        )
    return value


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


__all__ = [
    "CustomArrayRequirements",
    "CustomDataCoverage",
    "CustomDataCoverageError",
    "CustomDataProviderMap",
    "CustomDataProviderPort",
    "FixtureRecord",
    "InvalidLiveCustomDataCapabilityError",
    "InvalidLiveDataClientNameError",
    "KNOWN_CUSTOM_ARRAY_NAMES",
    "LiveCustomDataCapability",
    "LiveDataClientName",
    "ServedCustomData",
    "UnknownCustomArrayError",
    "UnknownCustomDataRecordError",
    "VOCABULARY",
    "AVAILABILITY_BY_VALUE",
    "arrays",
    "capture",
    "correct",
    "coverage",
    "ensure_arrays",
    "ingest",
    "records",
    "records_for_arrays",
]
