from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from typing import Generic, Protocol, TypeVar, cast

import pandas as pd

from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract, Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog


RecordT = TypeVar("RecordT", bound=Data)
_LOG = logging.getLogger(__name__)
_MAX_TIMESTAMP_NS = pd.Timestamp.max.value


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
    """One inclusive nanosecond window addressing part of a catalog dataset."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns > self.end_ns:
            raise ValueError("catalog interval start must not be after end")

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_ns, tz="UTC")

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.end_ns, tz="UTC")

    def from_frontier(self, oldest_verified: pd.Timestamp) -> "CatalogInterval | None":
        start_ns = max(self.start_ns, oldest_verified.value)
        if start_ns > self.end_ns:
            return None
        return CatalogInterval(start_ns, self.end_ns)


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

    def missing(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
    ) -> tuple[CatalogInterval, ...]:
        """The parts of *interval* this dataset has no answer for.

        One question, not two. Every write records the window it answered for
        — including a window that turned out to hold nothing — so the extents
        that name this dataset's files say what was *checked*, not merely what
        was *stored*. That is the same set the Nautilus data engine reads when
        deciding whether to fetch, which is why there is no second opinion to
        keep in step with.

        Answering from names rather than contents is what lets an empty
        verified window exist at all: it has no records to be inferred from.
        """
        unstored = self._store.get_missing_intervals_for_request(
            interval.start_ns,
            interval.end_ns,
            key.record_type,
            identifier=_identifier(key),
        )
        return tuple(CatalogInterval(start_ns, end_ns) for start_ns, end_ns in unstored)

    def covered_through(self, key: CatalogKey[RecordT]) -> int | None:
        """The latest point this dataset has an answer for, if it has one.

        Read from the same extents as :meth:`missing`, over the whole
        representable range, so a caller asking how far a dataset reaches and a
        caller asking what is absent inside a window cannot disagree.
        """
        missing = self.missing(key, CatalogInterval(0, _MAX_TIMESTAMP_NS))
        if not missing:
            return _MAX_TIMESTAMP_NS
        unanswered_tail = missing[-1]
        if unanswered_tail.start_ns == 0:
            return None
        return unanswered_tail.start_ns - 1

    def compact(self, key: CatalogKey[RecordT], interval: CatalogInterval) -> None:
        """Merge this dataset's files across an *interval* already answered for.

        The merged file is named for the span of the files it replaces, so
        compacting a run of adjacent windows preserves the coverage answer
        exactly. Compacting across a hole would not: the survivor's name would
        stretch over a window nobody checked. Every caller here compacts a
        range it has just seen answered end to end, so no hole is in reach.

        ``ensure_contiguous_files`` asks the vendor to check that before
        merging, which is why it is on. It is an ``assert``, so ``python -O``
        strips it — a guard against a writer regressing, not a guarantee.
        Do not reach for ``consolidate_data_by_period`` instead: it renames
        files to period boundaries or to record extents, and both rewrite the
        coverage answer rather than preserving it.
        """
        self._store.consolidate_data(
            key.record_type,
            identifier=_identifier(key),
            start=interval.start_ns,
            end=interval.end_ns,
            ensure_contiguous_files=True,
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
