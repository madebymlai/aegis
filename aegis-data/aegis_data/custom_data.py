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
)

VOCABULARY = frozenset(
    array_name
    for kind in _KINDS
    if kind.provisioned
    for array_name in kind.array_names
)


class UnknownCustomDataRecordError(ValueError):
    """The requested domain record has no Custom Data implementation."""


class CustomDataCoverageError(ValueError):
    """A requested custom-data window has never been completely ingested."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        missing: tuple[tuple[int, int], ...],
    ) -> None:
        self.instrument_id = instrument_id
        self.missing = missing
        super().__init__(
            f"custom data coverage is missing for {instrument_id.value}: {list(missing)}"
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
        _fill_in_provider_order(
            catalog,
            record_type,
            instrument_id,
            start=start,
            end=end,
            providers=providers,
            clock_ns=clock_ns,
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


def _fill_in_provider_order(
    catalog: ParquetDataCatalog,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: Sequence[CustomDataProviderPort[RecordT]],
    clock_ns: Callable[[], int],
) -> None:
    for provider in providers:
        missing = _missing_intervals(
            catalog,
            record_type,
            instrument_id,
            start_ns=start.value,
            end_ns=end.value,
        )
        for missing_start_ns, missing_end_ns in missing:
            _fill_interval(
                catalog,
                record_type,
                instrument_id,
                provider,
                start=pd.Timestamp(missing_start_ns, tz="UTC"),
                end=pd.Timestamp(missing_end_ns, tz="UTC"),
                clock_ns=clock_ns,
            )


def _fill_interval(
    catalog: ParquetDataCatalog,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    provider: CustomDataProviderPort[RecordT],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    clock_ns: Callable[[], int],
) -> None:
    served = provider.request_records(instrument_id, start=start, end=end)
    served_from = max(_utc(served.served_from), start)
    if served_from > end:
        return
    selected = tuple(
        sorted(
            (
                record
                for record in served.records
                if _record_belongs_to_interval(
                    record,
                    record_type=record_type,
                    instrument_id=instrument_id,
                    start=served_from,
                    end=end,
                )
            ),
            key=lambda record: record.ts_event,
        )
    )
    if not selected:
        _write_empty_marker(
            catalog,
            record_type,
            instrument_id,
            start=served_from,
            end=end,
            checked_at_ns=clock_ns(),
        )
        return
    catalog.write_data(
        list(selected),
        data_cls=record_type,
        identifier=instrument_id.value,
        start=served_from.value,
        end=end.value,
    )


def _record_belongs_to_interval(
    record: RecordT,
    *,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> bool:
    if not isinstance(record, record_type):
        raise TypeError(
            f"provider returned {type(record).__name__}, expected {record_type.__name__}"
        )
    if cast(InstrumentId, record.instrument_id) != instrument_id:
        raise ValueError("provider returned a custom-data record for another instrument")
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
) -> list[tuple[int, int]]:
    native_missing = catalog.get_missing_intervals_for_request(
        start_ns,
        end_ns,
        record_type,
        identifier=instrument_id.value,
    )
    empty_intervals = catalog.get_intervals(
        _CoverageMarker,
        identifier=_coverage_identifier(record_type, instrument_id),
    )
    return _subtract_covered(native_missing, empty_intervals)


def _subtract_covered(
    missing: Sequence[tuple[int, int]],
    covered: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    remaining = list(missing)
    for covered_start, covered_end in covered:
        next_remaining: list[tuple[int, int]] = []
        for start, end in remaining:
            if covered_end < start or covered_start > end:
                next_remaining.append((start, end))
                continue
            if start < covered_start:
                next_remaining.append((start, covered_start - 1))
            if covered_end < end:
                next_remaining.append((covered_end + 1, end))
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
    "ServedCustomData",
    "UnknownCustomDataRecordError",
    "VOCABULARY",
    "arrays",
    "correct",
    "coverage",
    "ingest",
    "records",
]
