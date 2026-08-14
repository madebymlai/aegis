from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Sequence
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


class _CatalogAwareEngine(Protocol):
    def register_catalog(
        self,
        catalog: _CatalogBackend,
        name: str = "catalog_0",
    ) -> None: ...


@dataclass(frozen=True)
class CatalogInterval:
    """One inclusive nanosecond window addressing part of a catalog dataset."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns > self.end_ns:
            raise ValueError("catalog interval start must not be after end")

    @classmethod
    def after(cls, frontier_ns: int, through_ns: int) -> "CatalogInterval":
        """Advance coverage with exact nanosecond adjacency.

        Coverage windows must tile: a previous window ends at ``T - 1`` and
        the next begins at ``T``. Nautilus permits gaps, so every frontier
        advance goes through this constructor rather than repeating arithmetic.
        """
        return cls(frontier_ns + 1, through_ns)

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_ns, tz="UTC")

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.end_ns, tz="UTC")


@dataclass(frozen=True)
class CatalogKey(Generic[RecordT]):
    """A durable dataset address whose serialized form is Catalog-private."""

    record_type: type[RecordT]
    _subject: InstrumentId | BarType

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


@dataclass(frozen=True)
class Catalog:
    """Domain-shaped owner of the Nautilus durable persistence boundary."""

    _store: _CatalogBackend

    @classmethod
    def open(cls, path: str | Path) -> Catalog:
        root = Path(path).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return cls(cast(_CatalogBackend, ParquetDataCatalog(root)))

    def register_with(self, engine: _CatalogAwareEngine) -> None:
        """Register this Catalog with a Nautilus data engine."""
        engine.register_catalog(self._store)

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
        """The parts of *interval* this dataset holds no file for.

        The extents naming a dataset's files, read as coverage. A write records
        the window it answered for, so for a dataset that carries records these
        extents say what was *checked*, not merely what was *stored* — and they
        are what the Nautilus data engine reads when deciding whether to fetch,
        so there is no second opinion to keep in step with.

        An empty window is recorded by extending a neighbouring file's name
        over it. If a dataset has never held a record, an empty write records
        nothing and the window remains missing; absence is still an empty read,
        so the only cost is a later request asking again.
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

        The vendor documents these intervals as "disjoint and sorted by start
        time", so the last one is the unanswered tail beyond everything held.
        """
        missing = self.missing(key, CatalogInterval(0, _MAX_TIMESTAMP_NS))
        if not missing:
            return _MAX_TIMESTAMP_NS
        unanswered_tail = missing[-1]
        if unanswered_tail.start_ns == 0:
            return None
        return unanswered_tail.start_ns - 1

    def compact(self, key: CatalogKey[RecordT], interval: CatalogInterval) -> None:
        """Merge the requested range, whose writer windows abut by one nanosecond.

        The merged file is named for the span of the adjacent files it replaces,
        preserving the Catalog's coverage answer. Production writers tile every
        requested missing interval exactly; they must end one window at ``T - 1``
        and begin the next at ``T``. Nautilus rejects overlap but permits gaps,
        so that nanosecond-adjacency requirement lives with this arithmetic and
        cannot be delegated to the vendor.
        """
        self._store.consolidate_data(
            key.record_type,
            identifier=_identifier(key),
            start=interval.start_ns,
            end=interval.end_ns,
            ensure_contiguous_files=True,
            deduplicate=True,
        )

    def fill(
        self,
        key: CatalogKey[RecordT],
        interval: CatalogInterval,
        fetch: Callable[[CatalogInterval], Sequence[RecordT]],
    ) -> None:
        """Obtain and store only the parts of *interval* this dataset lacks.

        The one fill algorithm, and the same one the Nautilus data engine runs
        for Bars: ask what is missing, request exactly that, record the window
        each request answered for, then merge into one file once the interval is
        whole. A caller supplies only how to obtain records for a gap; which
        gaps exist, what a write records, and when a merge is safe stay here.

        *fetch* is handed one gap at a time and returns the records belonging to
        it. A gap it cannot serve is an empty answer, still recorded as checked.
        """
        gaps = self.missing(key, interval)
        for gap in gaps:
            self.replace(key, gap, tuple(fetch(gap)))
        if gaps and not self.missing(key, interval):
            self.compact(key, interval)

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
    return list(records)


__all__ = ["Catalog", "CatalogInterval", "CatalogKey"]
