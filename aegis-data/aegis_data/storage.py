from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar, cast

from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract, Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog


RecordT = TypeVar("RecordT", bound=Data)
_LOG = logging.getLogger(__name__)


class _CatalogBackend(Protocol):
    def query(
        self,
        data_cls: type,
        identifiers: list[str] | None = None,
        start: object = None,
        end: object = None,
        **kwargs: object,
    ) -> list[object]: ...

    def write_data(
        self,
        data: list[object],
        start: int | None = None,
        end: int | None = None,
        data_cls: type | None = None,
        identifier: str | None = None,
        **kwargs: object,
    ) -> None: ...

    def delete_data_range(
        self,
        data_cls: type,
        identifier: str | None = None,
        start: object = None,
        end: object = None,
    ) -> None: ...

    def reset_data_file_names(
        self,
        data_cls: type,
        identifier: str | None = None,
    ) -> None: ...

    def get_missing_intervals_for_request(
        self,
        start: int,
        end: int,
        data_cls: type,
        identifier: str | None = None,
    ) -> list[tuple[int, int]]: ...

    def consolidate_data(
        self,
        data_cls: type,
        identifier: str | None = None,
        start: object = None,
        end: object = None,
        ensure_contiguous_files: bool = True,
        deduplicate: bool = False,
    ) -> None: ...

    def instruments(
        self,
        instrument_type: type | None = None,
        instrument_ids: list[str] | None = None,
        **kwargs: object,
    ) -> list[Instrument]: ...


@dataclass(frozen=True)
class CatalogInterval:
    start_ns: int
    end_ns: int


@dataclass(frozen=True)
class _CoverageSubject:
    key: CatalogKey[Data]


@dataclass(frozen=True)
class CatalogKey(Generic[RecordT]):
    """A durable dataset address whose serialized form is Catalog-private."""

    record_type: type[RecordT]
    _subject: InstrumentId | BarType | _CoverageSubject

    @classmethod
    def for_instrument(
        cls,
        record_type: type[RecordT],
        instrument_id: InstrumentId,
    ) -> CatalogKey[RecordT]:
        return cls(record_type, instrument_id)

    @classmethod
    def for_bar(cls, bar_type: BarType) -> CatalogKey[Bar]:
        return cls(Bar, bar_type)

    @classmethod
    def for_coverage(
        cls,
        record_type: type[RecordT],
        subject: CatalogKey[Data],
    ) -> CatalogKey[RecordT]:
        return cls(record_type, _CoverageSubject(subject))


@dataclass(frozen=True)
class Catalog:
    """Domain-shaped owner of the Nautilus durable persistence boundary."""

    _store: _CatalogBackend

    @classmethod
    def open(cls, path: str | Path) -> Catalog:
        root = Path(path).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return cls(ParquetDataCatalog(root))

    def replace(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
        records: tuple[RecordT, ...],
    ) -> None:
        identifier = _identifier(key)
        if self.missing(key, interval) != (interval,):
            self.drop(key, interval)
        if not records:
            return
        self._store.write_data(
            _records_for_write(key, records),
            data_cls=key.record_type,
            identifier=identifier,
            start=interval.start_ns,
            end=interval.end_ns,
        )

    def drop(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
    ) -> None:
        self._store.delete_data_range(
            key.record_type,
            identifier=_identifier(key),
            start=interval.start_ns,
            end=interval.end_ns,
        )
        self._store.reset_data_file_names(
            key.record_type,
            identifier=_identifier(key),
        )

    def missing(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
    ) -> tuple[CatalogInterval, ...]:
        missing = self._store.get_missing_intervals_for_request(
            interval.start_ns,
            interval.end_ns,
            key.record_type,
            identifier=_identifier(key),
        )
        return tuple(CatalogInterval(start_ns, end_ns) for start_ns, end_ns in missing)

    def compact(self, key: CatalogKey[RecordT], interval: CatalogInterval) -> None:
        """Merge this dataset's files across *interval*.

        Purely a storage operation: nothing reads coverage out of a filename,
        so merging across a gap cannot make an unchecked interval look checked.
        Files are free to be laid out however reads them fastest.

        ``ensure_contiguous_files`` is the vendor asking whether to assert the
        files are adjacent before merging — its only effect. A Catalog with a
        real hole in its history is an ordinary Catalog here, so there is
        nothing to assert; leaving it on would raise on a normal state, and
        only when the process happens not to be running under ``-O``.
        """
        self._store.consolidate_data(
            key.record_type,
            identifier=_identifier(key),
            start=interval.start_ns,
            end=interval.end_ns,
            ensure_contiguous_files=False,
            deduplicate=True,
        )

    def repair_interval_descriptions(self, key: CatalogKey[RecordT]) -> None:
        """Rebuild filename intervals from stored record extents."""
        self._store.reset_data_file_names(
            key.record_type,
            identifier=_identifier(key),
        )

    def read(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
    ) -> tuple[RecordT, ...]:
        queried = self._store.query(
            key.record_type,
            identifiers=[_identifier(key)],
            start=interval.start_ns,
            end=interval.end_ns,
        )
        records = (_record(item, key.record_type) for item in queried)
        by_ts_event = {record.ts_event: record for record in records}
        return tuple(by_ts_event[ts_event] for ts_event in sorted(by_ts_event))


    def read_all(self, key: CatalogKey[RecordT]) -> tuple[RecordT, ...]:
        queried = self._store.query(
            key.record_type,
            identifiers=[_identifier(key)],
        )
        records = (_record(item, key.record_type) for item in queried)
        by_ts_event = {record.ts_event: record for record in records}
        return tuple(by_ts_event[ts_event] for ts_event in sorted(by_ts_event))

    def definitions(
        self,
        instrument_ids: Sequence[InstrumentId],
    ) -> tuple[Instrument, ...]:
        return tuple(
            self._store.instruments(
                instrument_ids=[instrument_id.value for instrument_id in instrument_ids]
            )
        )

    def futures_for_root(self, root: str) -> tuple[FuturesContract, ...]:
        return tuple(
            instrument
            for instrument in self._store.instruments(instrument_type=FuturesContract)
            if isinstance(instrument, FuturesContract) and instrument.underlying == root
        )

    def store_definitions(self, instruments: Sequence[Instrument]) -> None:
        if instruments:
            self._store.write_data(list(instruments))


def _identifier(key: CatalogKey[Data]) -> str:
    if isinstance(key._subject, BarType):
        return str(key._subject)
    if isinstance(key._subject, _CoverageSubject):
        covered = key._subject.key
        if isinstance(covered._subject, BarType):
            return f"Bar-{covered._subject}"
        if isinstance(covered._subject, InstrumentId):
            return f"{covered.record_type.__name__}-{covered._subject.value}"
        raise TypeError("coverage keys cannot address the coverage dataset")
    return key._subject.value


def _record(item: object, record_type: type[RecordT]) -> RecordT:
    value = item.data if hasattr(item, "data") else item
    if not isinstance(value, record_type):
        raise TypeError(
            f"catalog returned {type(value).__name__}, expected {record_type.__name__}"
        )
    return cast(RecordT, value)


def _records_for_write(
    key: CatalogKey[RecordT],
    records: tuple[RecordT, ...],
) -> list[object]:
    if not isinstance(key._subject, _CoverageSubject):
        return list(records)
    identifier = InstrumentId.from_str(_identifier(key))
    for record in records:
        record.instrument_id = identifier
    return list(records)


__all__ = ["Catalog", "CatalogInterval", "CatalogKey"]
