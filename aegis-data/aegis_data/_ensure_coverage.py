"""One internal Ensure Coverage engine for every catalog record type."""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

import pandas as pd


class CoverageCatalog(Protocol):
    """Only the catalog commands needed by Ensure Coverage."""

    def write_data(
        self,
        data: list[Any],
        start: int | None = None,
        end: int | None = None,
        data_cls: type | None = None,
        identifier: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class CoverageInterval:
    """One inclusive nanosecond interval whose catalog coverage is missing."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns > self.end_ns:
            raise ValueError("coverage interval start must not be after end")

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_ns, tz="UTC")

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.end_ns, tz="UTC")

    def from_frontier(self, served_from: pd.Timestamp) -> "CoverageInterval | None":
        start_ns = max(self.start_ns, served_from.value)
        if start_ns > self.end_ns:
            return None
        return CoverageInterval(start_ns, self.end_ns)


RecordT = TypeVar("RecordT")
MissingIntervals = Callable[[], list[CoverageInterval]]
CoverageError = Callable[[Sequence[CoverageInterval]], Exception]
ProviderBoundary = Callable[[str], AbstractContextManager[None]]
VerifiedIntervalWriter = Callable[[CoverageInterval], None]
CoverageSuccess = Callable[[], None]
Consolidator = Callable[[], None]
RecordSelector = Callable[[Sequence[RecordT], CoverageInterval], Sequence[RecordT]]


@dataclass(frozen=True)
class ServedRecords(Generic[RecordT]):
    """One provider's records and oldest source-verified instant."""

    records: tuple[RecordT, ...]
    served_from: pd.Timestamp


RecordFetcher = Callable[[pd.Timestamp, pd.Timestamp], ServedRecords[RecordT]]


def ensure_coverage(
    catalog: CoverageCatalog,
    *,
    data_cls: type,
    identifier: str,
    subject: str,
    fetchers: Sequence[RecordFetcher[Any]],
    missing_intervals: MissingIntervals,
    coverage_error: CoverageError,
    provider_boundary: ProviderBoundary,
    consolidate: Consolidator,
    verified_interval_writer: VerifiedIntervalWriter | None = None,
    on_coverage_filled: CoverageSuccess | None = None,
    select_records: RecordSelector[Any] | None = None,
) -> None:
    """Fill and re-verify one requested catalog window.

    Fetchers are tried in order and each fills only what earlier ones left
    missing (fill-order). A verified-interval writer can record provider
    verification independently of whether the provider returned any records.
    An *environmental* failure raised inside
    ``provider_boundary`` (gateway drop, timeout) aborts the whole request —
    deliberately: providers here are complementary (each owns a window), not
    redundant failover, so a source that cannot even be reached fails closed
    rather than silently deferring to a lesser source. Add catch-and-continue
    only when a genuinely redundant provider exists, with a test pinning which
    semantic is wanted.

    The injected consolidator owns which physical dataset represents coverage:
    bars consolidate their record files, while sparse Custom Data consolidates
    its generic checked-interval records.
    """
    initial_missing = missing_intervals()
    if not initial_missing:
        return
    if not fetchers:
        raise coverage_error(initial_missing)

    for fetch in fetchers:
        for missing in missing_intervals():
            with provider_boundary(subject):
                served = fetch(missing.start, missing.end)
            verified = missing.from_frontier(served.served_from)
            if verified is None:
                continue
            records = tuple(
                served.records
                if select_records is None
                else select_records(served.records, verified)
            )
            if records:
                catalog.write_data(
                    list(records),
                    data_cls=data_cls,
                    identifier=identifier,
                    start=verified.start_ns,
                    end=verified.end_ns,
                )
            if verified_interval_writer is not None:
                verified_interval_writer(verified)

    consolidate()
    remaining = missing_intervals()
    if remaining:
        raise coverage_error(remaining)
    if on_coverage_filled is not None:
        with provider_boundary(subject):
            on_coverage_filled()


__all__ = ["CoverageInterval", "ServedRecords", "ensure_coverage"]
