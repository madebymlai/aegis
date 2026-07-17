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
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from aegis_data._ensure_coverage import (
    CoverageInterval,
    ServedRecords,
    ensure_coverage,
)
from aegis_data.catalog import CatalogCoverageGapError, gap_fill_boundary
from aegis_data._distribution_verification import DistributionVerification
from aegis_data.distributions import Distribution


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

@customdataclass
class _CoverageMarker(Data):
    """A checked interval for one typed kind."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    record_type: str = ""
    start_ns: int = 0
    end_ns: int = 0
    checked_at_ns: int = 0
    applicable: bool = True

RecordT = TypeVar("RecordT", bound=Data)


class _Applicability(Protocol):
    @property
    def applicable(self) -> bool: ...

    @property
    def definition(self) -> Any | None: ...


class _VerificationHook(Protocol):
    subject: str

    def provider_for(self, providers: Sequence[object]) -> object | None: ...

    def applicability(
        self, catalog: Any, instrument_id: InstrumentId
    ) -> _Applicability: ...

    def coverage_end(
        self,
        catalog: Any,
        mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> int: ...

    def verify(
        self,
        catalog: Any,
        provider: object,
        instrument_id: InstrumentId,
        definition: Any,
        interval: CoverageInterval,
        *,
        ensure_bar_coverage: Callable[[BarType, int, int], None],
    ) -> tuple[Data, ...]: ...

    def provider_missing_message(
        self, instrument_id: InstrumentId, missing: Sequence[CoverageInterval]
    ) -> str: ...

    def force_provider_message(self) -> str: ...


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


@dataclass(frozen=True)
class _VerifiedRecordKind:
    record_type: type[Data]
    verification: _VerificationHook
    provisioned: bool = True

    @property
    def array_names(self) -> tuple[()]:
        return ()


type _Kind = _ArrayKind | _VerifiedRecordKind


@dataclass(frozen=True)
class _Assessment:
    kind: _VerifiedRecordKind
    instrument_id: InstrumentId
    applicability: _Applicability
    interval: CoverageInterval


@dataclass(frozen=True)
class _VerificationFailure:
    subject: str
    detail: str


_KINDS: tuple[_Kind, ...] = (
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
    _VerifiedRecordKind(
        record_type=Distribution,
        verification=DistributionVerification(),
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
    if isinstance(kind, _ArrayKind)
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


@dataclass(frozen=True)
class VerifiedRecordRequirements:
    """Records and coverage rows produced by one generic verification pass."""

    records: tuple[Data, ...]
    coverage: tuple[dict[str, Any], ...]


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


def verify_record_requirements(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    providers: Sequence[object],
    clock_ns: Callable[[], int],
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> None:
    """Ensure every arrays-less kind is verified for the requested window."""
    requested = CoverageInterval(_timestamp_ns(start), _timestamp_ns(end))
    failures: dict[str, list[str]] = {}
    for assessment in _record_assessments(
        catalog, instrument_ids, requested, mark_bars=mark_bars
    ):
        failure = _verify_assessment(
            catalog,
            assessment,
            providers=providers,
            clock_ns=clock_ns,
            ensure_bar_coverage=ensure_bar_coverage,
        )
        if failure is not None:
            failures.setdefault(failure.subject, []).append(failure.detail)
    if failures:
        raise CatalogCoverageGapError(
            "; ".join(
                f"{subject} coverage is missing for "
                + "; ".join(sorted(subject_failures))
                for subject, subject_failures in sorted(failures.items())
            )
        )


def read_record_requirements(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> VerifiedRecordRequirements:
    """Read verified arrays-less records and their coverage provenance."""
    requested = CoverageInterval(_timestamp_ns(start), _timestamp_ns(end))
    assessments = _record_assessments(
        catalog, instrument_ids, requested, mark_bars=mark_bars
    )
    records = tuple(
        record
        for assessment in assessments
        if assessment.applicability.applicable
        for record in _catalog_records(
            catalog,
            assessment.kind.record_type,
            assessment.instrument_id,
            assessment.interval,
        )
    )
    return VerifiedRecordRequirements(
        records=records,
        coverage=tuple(
            _coverage_row(catalog, assessment) for assessment in assessments
        ),
    )


def record_coverage_report(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp | None,
    end: str | int | pd.Timestamp | None,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> tuple[dict[str, Any], ...]:
    """Report coverage for arrays-less kinds without fetching or mutating."""
    if start is None or end is None:
        return ()
    return tuple(
        _coverage_row(catalog, assessment)
        for assessment in _record_assessments(
            catalog,
            instrument_ids,
            CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
            mark_bars=mark_bars,
        )
    )


def force_reverify_record_requirements(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    providers: Sequence[object],
    clock_ns: Callable[[], int],
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> None:
    """Correct one bounded verification window through each kind's hook."""
    requested = CoverageInterval(_timestamp_ns(start), _timestamp_ns(end))
    for kind in _verification_kinds():
        hook = kind.verification
        provider = hook.provider_for(providers)
        if provider is None:
            raise CatalogCoverageGapError(hook.force_provider_message())
        for instrument_id in _dedupe(instrument_ids):
            catalog.delete_data_range(
                _CoverageMarker,
                identifier=_coverage_identifier(kind.record_type, instrument_id),
                start=requested.start_ns,
                end=requested.end_ns,
            )
            assessment = _assess_kind(
                catalog,
                kind,
                instrument_id,
                interval=requested,
                mark_bars=mark_bars,
                clamp=False,
            )
            failure = _verify_assessment(
                catalog,
                assessment,
                providers=(provider,),
                clock_ns=clock_ns,
                ensure_bar_coverage=ensure_bar_coverage,
            )
            if failure is not None:
                raise CatalogCoverageGapError(
                    f"{failure.subject} coverage is missing for {failure.detail}"
                )


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
                checked_at_ns=_checked_at(
                    catalog, record_type, instrument_id, start, end
                ),
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


def _kind_for(record_type: type[Data]) -> _Kind:
    for kind in _KINDS:
        if kind.record_type is record_type:
            return kind
    raise UnknownCustomDataRecordError(record_type.__name__)


def _kind_for_array_names(array_names: Sequence[str]) -> _ArrayKind:
    requested = set(array_names)
    for kind in _KINDS:
        if isinstance(kind, _ArrayKind) and requested <= set(kind.array_names):
            return kind
    raise UnknownCustomArrayError(sorted(requested))


def _kinds_for_array_names(array_names: Sequence[str]) -> tuple[_ArrayKind, ...]:
    requested = set(array_names)
    kinds = tuple(
        kind
        for kind in _KINDS
        if isinstance(kind, _ArrayKind) and requested.intersection(kind.array_names)
    )
    resolved = {name for kind in kinds for name in kind.array_names}
    unknown = sorted(requested - resolved)
    if unknown:
        raise UnknownCustomArrayError(unknown)
    return kinds


def _verification_kinds() -> tuple[_VerifiedRecordKind, ...]:
    return tuple(kind for kind in _KINDS if isinstance(kind, _VerifiedRecordKind))


def _record_assessments(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    interval: CoverageInterval,
    *,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> tuple[_Assessment, ...]:
    return tuple(
        _assess_kind(
            catalog,
            kind,
            instrument_id,
            interval=interval,
            mark_bars=mark_bars,
        )
        for kind in _verification_kinds()
        for instrument_id in _dedupe(instrument_ids)
    )


def _assess_kind(
    catalog: Any,
    kind: _VerifiedRecordKind,
    instrument_id: InstrumentId,
    interval: CoverageInterval,
    *,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    clamp: bool = True,
) -> _Assessment:
    hook = kind.verification
    applicability = hook.applicability(catalog, instrument_id)
    coverage_end = interval.end_ns
    if clamp and applicability.applicable:
        coverage_end = hook.coverage_end(
            catalog,
            mark_bars,
            instrument_id,
            interval,
        )
    return _Assessment(
        kind,
        instrument_id,
        applicability,
        CoverageInterval(interval.start_ns, coverage_end),
    )


def _verify_assessment(
    catalog: Any,
    assessment: _Assessment,
    *,
    providers: Sequence[object],
    clock_ns: Callable[[], int],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> _VerificationFailure | None:
    hook = assessment.kind.verification
    missing = _marker_missing(catalog, assessment)
    if not missing:
        return None
    if not assessment.applicability.applicable:
        checked_at_ns = clock_ns()
        for interval in missing:
            _write_verification_marker(
                catalog,
                assessment.kind.record_type,
                assessment.instrument_id,
                interval=interval,
                checked_at_ns=checked_at_ns,
                applicable=False,
            )
        return None
    provider = hook.provider_for(providers)
    if provider is None:
        return _VerificationFailure(
            hook.subject,
            hook.provider_missing_message(assessment.instrument_id, missing),
        )
    checked_at_ns = clock_ns()
    for interval in missing:
        with gap_fill_boundary(f"{hook.subject}s for {assessment.instrument_id.value}"):
            replacement = hook.verify(
                catalog,
                provider,
                assessment.instrument_id,
                assessment.applicability.definition,
                interval,
                ensure_bar_coverage=ensure_bar_coverage,
            )
        _replace_catalog_records(
            catalog,
            assessment.kind.record_type,
            assessment.instrument_id,
            replacement,
            interval=interval,
        )
        _write_verification_marker(
            catalog,
            assessment.kind.record_type,
            assessment.instrument_id,
            interval=interval,
            checked_at_ns=checked_at_ns,
            applicable=True,
        )
    return None


def _replace_catalog_records(
    catalog: Any,
    record_type: type[Data],
    instrument_id: InstrumentId,
    replacement: Sequence[Data],
    interval: CoverageInterval,
) -> None:
    catalog.delete_data_range(
        record_type,
        identifier=instrument_id.value,
        start=interval.start_ns,
        end=interval.end_ns,
    )
    selected = [
        _validate_record(
            record,
            record_type=record_type,
            instrument_id=instrument_id,
        )
        for record in replacement
        if interval.start_ns <= record.ts_event <= interval.end_ns
    ]
    if selected:
        catalog.write_data(
            selected,
            data_cls=record_type,
            identifier=instrument_id.value,
            start=interval.start_ns,
            end=interval.end_ns,
        )


def _marker_missing(catalog: Any, assessment: _Assessment) -> list[CoverageInterval]:
    return [
        CoverageInterval(start_ns, end_ns)
        for start_ns, end_ns in catalog.get_missing_intervals_for_request(
            assessment.interval.start_ns,
            assessment.interval.end_ns,
            _CoverageMarker,
            identifier=_coverage_identifier(
                assessment.kind.record_type, assessment.instrument_id
            ),
        )
    ]


def _coverage_row(catalog: Any, assessment: _Assessment) -> dict[str, Any]:
    return {
        "instrument_id": assessment.instrument_id.value,
        "applicable": assessment.applicability.applicable,
        "verified_start": _timestamp_text(assessment.interval.start_ns),
        "verified_end": _timestamp_text(assessment.interval.end_ns),
        "event_count": len(
            _catalog_records(
                catalog,
                assessment.kind.record_type,
                assessment.instrument_id,
                assessment.interval,
            )
        )
        if assessment.applicability.applicable
        else 0,
        "checked_at": _marker_checked_at(catalog, assessment),
    }


def _catalog_records(
    catalog: Any,
    record_type: type[RecordT],
    instrument_id: InstrumentId,
    interval: CoverageInterval,
) -> tuple[RecordT, ...]:
    return tuple(
        sorted(
            (
                _as_record(item, record_type)
                for item in catalog.query(
                    record_type,
                    identifiers=[instrument_id.value],
                    start=interval.start_ns,
                    end=interval.end_ns,
                )
            ),
            key=lambda record: record.ts_event,
        )
    )


def _marker_checked_at(catalog: Any, assessment: _Assessment) -> str | None:
    checked = _checked_at_values(
        catalog,
        assessment.kind.record_type,
        assessment.instrument_id,
        assessment.interval,
    )
    return _timestamp_text(min(checked)) if checked else None


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
    empty_intervals = [
        CoverageInterval(empty_start, empty_end)
        for empty_start, empty_end in catalog.get_intervals(
            _CoverageMarker,
            identifier=_coverage_identifier(record_type, instrument_id),
        )
    ]
    return _subtract_covered(native_missing, empty_intervals)


def _subtract_covered(
    missing: Sequence[CoverageInterval],
    covered: Sequence[CoverageInterval],
) -> list[CoverageInterval]:
    remaining = list(missing)
    for covered_interval in covered:
        next_remaining: list[CoverageInterval] = []
        for interval in remaining:
            if (
                covered_interval.end_ns < interval.start_ns
                or covered_interval.start_ns > interval.end_ns
            ):
                next_remaining.append(interval)
                continue
            if interval.start_ns < covered_interval.start_ns:
                next_remaining.append(
                    CoverageInterval(interval.start_ns, covered_interval.start_ns - 1)
                )
            if covered_interval.end_ns < interval.end_ns:
                next_remaining.append(
                    CoverageInterval(covered_interval.end_ns + 1, interval.end_ns)
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
    _write_verification_marker(
        catalog,
        record_type,
        instrument_id,
        interval=CoverageInterval(start.value, end.value),
        checked_at_ns=checked_at_ns,
        applicable=True,
    )


def _write_verification_marker(
    catalog: Any,
    record_type: type[Data],
    instrument_id: InstrumentId,
    interval: CoverageInterval,
    *,
    checked_at_ns: int,
    applicable: bool,
) -> None:
    marker_points = (
        (interval.start_ns,)
        if interval.start_ns == interval.end_ns
        else (interval.start_ns, interval.end_ns)
    )
    markers = [
        _CoverageMarker(
            point,
            point,
            instrument_id=_coverage_instrument_id(record_type, instrument_id),
            record_type=record_type.__name__,
            start_ns=interval.start_ns,
            end_ns=interval.end_ns,
            checked_at_ns=checked_at_ns,
            applicable=applicable,
        )
        for point in marker_points
    ]
    catalog.write_data(
        markers,
        data_cls=_CoverageMarker,
        identifier=_coverage_identifier(record_type, instrument_id),
        start=interval.start_ns,
        end=interval.end_ns,
    )


def _checked_at(
    catalog: ParquetDataCatalog,
    record_type: type[Data],
    instrument_id: InstrumentId,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> int | None:
    checked = _checked_at_values(
        catalog,
        record_type,
        instrument_id,
        CoverageInterval(start.value, end.value),
    )
    return max(checked, default=None)


def _checked_at_values(
    catalog: Any,
    record_type: type[Data],
    instrument_id: InstrumentId,
    interval: CoverageInterval,
) -> list[int]:
    markers = catalog.query(
        _CoverageMarker,
        identifiers=[_coverage_identifier(record_type, instrument_id)],
        start=interval.start_ns,
        end=interval.end_ns,
    )
    return [
        marker.checked_at_ns
        for item in markers
        for marker in [_as_record(item, _CoverageMarker)]
        if marker.end_ns >= interval.start_ns and marker.start_ns <= interval.end_ns
    ]


def _coverage_identifier(record_type: type[Data], instrument_id: InstrumentId) -> str:
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
        raise TypeError(
            f"catalog returned {type(value).__name__}, expected {record_type.__name__}"
        )
    return value


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _timestamp_ns(value: str | int | pd.Timestamp) -> int:
    if isinstance(value, int):
        return value
    return _utc(pd.Timestamp(value)).value


def _timestamp_text(value: int) -> str:
    return pd.Timestamp(value, tz="UTC").isoformat()


def _dedupe(instrument_ids: Sequence[InstrumentId]) -> tuple[InstrumentId, ...]:
    return tuple(dict.fromkeys(instrument_ids))


__all__ = [
    "CustomDataCoverage",
    "CustomDataCoverageError",
    "CustomDataProviderPort",
    "FixtureRecord",
    "KNOWN_CUSTOM_ARRAY_NAMES",
    "ServedCustomData",
    "VerifiedRecordRequirements",
    "UnknownCustomArrayError",
    "UnknownCustomDataRecordError",
    "VOCABULARY",
    "AVAILABILITY_BY_VALUE",
    "arrays",
    "correct",
    "coverage",
    "ingest",
    "records",
    "records_for_arrays",
    "read_record_requirements",
    "record_coverage_report",
    "force_reverify_record_requirements",
    "verify_record_requirements",
]
