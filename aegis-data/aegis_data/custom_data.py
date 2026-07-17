"""Provider-neutral storage and ingestion of typed adjacent market data.

The interface deals only in domain records, provider ports, instruments, time
windows, and a catalog root. Nautilus interval and serialization machinery is
kept inside this module.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar, cast

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
    array_names: tuple[str, ...]


_KINDS = (
    _Kind(
        record_type=FixtureRecord,
        array_names=("FixtureValue", "FixtureAvailable", "FixtureAgeDays"),
    ),
)


class UnknownCustomDataRecordError(ValueError):
    """The requested domain record has no Custom Data implementation."""


def ingest(
    record_type: type[RecordT],
    instrument_ids: Sequence[InstrumentId],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    providers: Sequence[CustomDataProviderPort[RecordT]],
    catalog_path: Path,
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
        )


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
) -> None:
    for provider in providers:
        missing = catalog.get_missing_intervals_for_request(
            start.value,
            end.value,
            record_type,
            identifier=instrument_id.value,
        )
        for missing_start_ns, missing_end_ns in missing:
            _fill_interval(
                catalog,
                record_type,
                instrument_id,
                provider,
                start=pd.Timestamp(missing_start_ns, tz="UTC"),
                end=pd.Timestamp(missing_end_ns, tz="UTC"),
            )


def _fill_interval(
    catalog: ParquetDataCatalog,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    provider: CustomDataProviderPort[RecordT],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
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
    "CustomDataProviderPort",
    "FixtureRecord",
    "ServedCustomData",
    "UnknownCustomDataRecordError",
    "ingest",
    "records",
]
