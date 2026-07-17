"""Provider-neutral storage and ingestion of typed adjacent market data.

The interface deals only in domain records, provider ports, instruments, time
windows, and a catalog root. Nautilus interval and serialization machinery is
kept inside this module.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import time_ns
from typing import Any, Callable, Generic, Protocol, TypeVar, cast

import pandas as pd
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

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

    @classmethod
    def schema(cls) -> Any:
        return cls._schema


@customdataclass
class _DormantFixtureRecord(Data):
    """Known fixture shape with deliberately absent provider wiring."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    value: float = 0.0

    @classmethod
    def schema(cls) -> Any:
        return cls._schema


@customdataclass
class _CoverageMarker(Data):
    """A checked interval that contained no records for one typed kind."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    record_type: str = ""
    start_ns: int = 0
    end_ns: int = 0
    checked_at_ns: int = 0

    @classmethod
    def schema(cls) -> Any:
        return cls._schema


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


@dataclass(frozen=True)
class _Kind:
    record_type: type[Data]
    value_array: str
    availability_array: str
    age_array: str
    value_attribute: str
    provisioned: bool

    @property
    def array_names(self) -> tuple[str, ...]:
        return (self.value_array, self.availability_array, self.age_array)


_KINDS = (
    _Kind(
        record_type=FixtureRecord,
        value_array="FixtureValue",
        availability_array="FixtureAvailable",
        age_array="FixtureAgeDays",
        value_attribute="value",
        provisioned=True,
    ),
    _Kind(
        record_type=_DormantFixtureRecord,
        value_array="DormantFixtureValue",
        availability_array="DormantFixtureAvailable",
        age_array="DormantFixtureAgeDays",
        value_attribute="value",
        provisioned=False,
    ),
)

KNOWN_CUSTOM_ARRAY_NAMES = frozenset(
    array_name for kind in _KINDS for array_name in kind.array_names
)
VOCABULARY = frozenset(
    array_name
    for kind in _KINDS
    if kind.provisioned
    for array_name in kind.array_names
)
AVAILABILITY_BY_VALUE = {
    kind.value_array: kind.availability_array for kind in _KINDS
}


class UnknownCustomDataRecordError(ValueError):
    """The requested domain record has no Custom Data implementation."""


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
    ensure_coverage(
        catalog,
        data_cls=record_type,
        identifier=instrument_id.value,
        subject=f"custom data for {instrument_id.value}",
        fetchers=tuple(
            _record_fetcher(provider, instrument_id, record_type)
            for provider in providers
        ),
        missing_intervals=lambda: _missing_intervals(
            catalog,
            record_type,
            instrument_id,
            start_ns=requested.start_ns,
            end_ns=requested.end_ns,
        ),
        coverage_error=lambda missing: CustomDataCoverageError(
            instrument_id, tuple(missing)
        ),
        provider_boundary=gap_fill_boundary,
        empty_interval_writer=lambda empty: _write_empty_marker(
            catalog,
            record_type,
            instrument_id,
            start=empty.start,
            end=empty.end,
            checked_at_ns=clock_ns(),
        ),
        consolidation_interval=requested,
        select_records=_records_within_event_window,
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
    catalog.delete_data_range(
        record_type,
        identifier=instrument_id.value,
        start=start,
        end=end,
    )
    catalog.delete_data_range(
        _CoverageMarker,
        identifier=_coverage_identifier(record_type, instrument_id),
        start=start,
        end=end,
    )
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
        return
    _write_empty_marker(
        catalog,
        record_type,
        instrument_id,
        start=start,
        end=end,
        checked_at_ns=clock_ns(),
    )


def arrays(
    array_names: Sequence[str],
    instrument_ids: Sequence[InstrumentId],
    *,
    index: pd.DatetimeIndex,
    catalog_path: Path,
) -> dict[str, pd.DataFrame]:
    """Project the latest causally known record onto the caller's exact index."""
    kind = _kind_for_array_names(array_names)
    if len(index) == 0:
        return {
            name: pd.DataFrame(index=index, columns=instrument_ids, dtype=float)
            for name in array_names
        }
    coverage(
        cast(type[Data], kind.record_type),
        instrument_ids,
        start=pd.Timestamp(index[0]),
        end=pd.Timestamp(index[-1]),
        catalog_path=catalog_path,
    )
    panels = {
        name: pd.DataFrame(0.0, index=index, columns=instrument_ids)
        for name in array_names
    }
    stored = records(
        kind.record_type,
        instrument_ids,
        start=pd.Timestamp(index[0]),
        end=pd.Timestamp(index[-1]),
        catalog_path=catalog_path,
    )
    _project_records(kind, stored, instrument_ids, index, panels)
    return panels


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
    start = _utc(start)
    end = _utc(end)
    reports: list[CustomDataCoverage] = []
    for instrument_id in instrument_ids:
        missing = tuple(
            _missing_intervals(
                catalog,
                record_type,
                instrument_id,
                start_ns=start.value,
                end_ns=end.value,
            )
        )
        if missing:
            raise CustomDataCoverageError(instrument_id, missing)
        reports.append(
            CustomDataCoverage(
                instrument_id=instrument_id,
                checked_at_ns=_checked_at(catalog, record_type, instrument_id, start, end),
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
    catalog = ParquetDataCatalog(str(catalog_path))
    stored: list[RecordT] = []
    for instrument_id in instrument_ids:
        queried = catalog.query(
            record_type,
            identifiers=[instrument_id.value],
            start=_utc(start),
            end=_utc(end),
        )
        stored.extend(_as_record(item, record_type) for item in queried)
    return tuple(
        sorted(
            stored,
            key=lambda item: (cast(InstrumentId, item.instrument_id).value, item.ts_event),
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
        raise ValueError("provider returned a custom-data record for another instrument")
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


def _kind_for(record_type: type[Data]) -> _Kind:
    for kind in _KINDS:
        if kind.record_type is record_type:
            return kind
    raise UnknownCustomDataRecordError(record_type.__name__)


def _kind_for_array_names(array_names: Sequence[str]) -> _Kind:
    requested = set(array_names)
    for kind in _KINDS:
        if requested <= set(kind.array_names):
            return kind
    raise ValueError(f"unknown custom arrays: {sorted(requested)}")


def _project_records(
    kind: _Kind,
    stored: Sequence[Data],
    instrument_ids: Sequence[InstrumentId],
    index: pd.DatetimeIndex,
    panels: dict[str, pd.DataFrame],
) -> None:
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
            if kind.value_array in panels:
                panels[kind.value_array].at[row, instrument_id] = float(
                    getattr(current, kind.value_attribute)
                )
            if kind.availability_array in panels:
                panels[kind.availability_array].at[row, instrument_id] = 1.0
            if kind.age_array in panels:
                panels[kind.age_array].at[row, instrument_id] = (
                    row_ns - current.ts_event
                ) / 86_400_000_000_000


def _missing_intervals(
    catalog: ParquetDataCatalog,
    record_type: type[Data],
    instrument_id: InstrumentId,
    *,
    start_ns: int,
    end_ns: int,
) -> list[CoverageInterval]:
    native_missing = [
        CoverageInterval(missing_start, missing_end)
        for missing_start, missing_end in catalog.get_missing_intervals_for_request(
            start_ns,
            end_ns,
            record_type,
            identifier=instrument_id.value,
        )
    ]
    empty_intervals = catalog.get_intervals(
        _CoverageMarker,
        identifier=_coverage_identifier(record_type, instrument_id),
    )
    return _subtract_covered(native_missing, empty_intervals)


def _subtract_covered(
    missing: Sequence[CoverageInterval],
    covered: Sequence[tuple[int, int]],
) -> list[CoverageInterval]:
    remaining = list(missing)
    for covered_start, covered_end in covered:
        next_remaining: list[CoverageInterval] = []
        for interval in remaining:
            if covered_end < interval.start_ns or covered_start > interval.end_ns:
                next_remaining.append(interval)
                continue
            if interval.start_ns < covered_start:
                next_remaining.append(
                    CoverageInterval(interval.start_ns, covered_start - 1)
                )
            if covered_end < interval.end_ns:
                next_remaining.append(
                    CoverageInterval(covered_end + 1, interval.end_ns)
                )
        remaining = next_remaining
    return remaining


def _write_empty_marker(
    catalog: ParquetDataCatalog,
    record_type: type[Data],
    instrument_id: InstrumentId,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    checked_at_ns: int,
) -> None:
    marker = _CoverageMarker(
        checked_at_ns,
        checked_at_ns,
        instrument_id=_coverage_instrument_id(record_type, instrument_id),
        record_type=record_type.__name__,
        start_ns=start.value,
        end_ns=end.value,
        checked_at_ns=checked_at_ns,
    )
    catalog.write_data(
        [marker],
        data_cls=_CoverageMarker,
        identifier=_coverage_identifier(record_type, instrument_id),
        start=start.value,
        end=end.value,
    )


def _checked_at(
    catalog: ParquetDataCatalog,
    record_type: type[Data],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> int | None:
    markers = catalog.query(
        _CoverageMarker,
        identifiers=[_coverage_identifier(record_type, instrument_id)],
    )
    checked = [
        marker.checked_at_ns
        for item in markers
        for marker in [_as_record(item, _CoverageMarker)]
        if marker.end_ns >= start.value and marker.start_ns <= end.value
    ]
    return max(checked, default=None)


def _coverage_identifier(
    record_type: type[Data], instrument_id: InstrumentId
) -> str:
    return _coverage_instrument_id(record_type, instrument_id).value


def _coverage_instrument_id(
    record_type: type[Data], instrument_id: InstrumentId
) -> InstrumentId:
    return InstrumentId.from_str(
        f"{record_type.__name__}-{instrument_id.symbol.value}.{instrument_id.venue.value}"
    )


def _as_record(item: object, record_type: type[RecordT]) -> RecordT:
    value = item.data if hasattr(item, "data") else item
    if not isinstance(value, record_type):
        raise TypeError(f"catalog returned {type(value).__name__}, expected {record_type.__name__}")
    return value


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


__all__ = [
    "CustomDataCoverage",
    "CustomDataCoverageError",
    "CustomDataProviderPort",
    "FixtureRecord",
    "KNOWN_CUSTOM_ARRAY_NAMES",
    "ServedCustomData",
    "UnknownCustomDataRecordError",
    "VOCABULARY",
    "AVAILABILITY_BY_VALUE",
    "arrays",
    "correct",
    "coverage",
    "ingest",
    "records",
]
