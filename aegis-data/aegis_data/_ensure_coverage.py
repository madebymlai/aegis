"""One internal Ensure Coverage engine for every catalog record type."""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, TypeVar

import pandas as pd

from aegis_data.provider import ProviderAnswer


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

    def from_frontier(
        self, oldest_verified: pd.Timestamp
    ) -> "CoverageInterval | None":
        start_ns = max(self.start_ns, oldest_verified.value)
        if start_ns > self.end_ns:
            return None
        return CoverageInterval(start_ns, self.end_ns)


RecordT = TypeVar("RecordT")
MissingIntervals = Callable[[], list[CoverageInterval]]
CoverageError = Callable[[Sequence[CoverageInterval]], Exception]
ProviderBoundary = Callable[[str], AbstractContextManager[None]]
CoverageSuccess = Callable[[], None]
CoverageCommit = Callable[[CoverageInterval, tuple[RecordT, ...]], None]
CoverageFinalizer = Callable[[], None]
RecordSelector = Callable[[Sequence[RecordT], CoverageInterval], Sequence[RecordT]]


RecordFetcher = Callable[[pd.Timestamp, pd.Timestamp], ProviderAnswer[RecordT]]


def ensure_coverage(
    *,
    subject: str,
    provider: RecordFetcher[Any] | None,
    missing_intervals: MissingIntervals,
    commit: CoverageCommit[Any],
    finalize: CoverageFinalizer,
    coverage_error: CoverageError,
    provider_boundary: ProviderBoundary,
    on_coverage_filled: CoverageSuccess | None = None,
    select_records: RecordSelector[Any] | None = None,
) -> None:
    """Fill and re-verify one requested catalog window.

    One provider answers every initially missing interval. The caller commits
    every provider-verified interval, including empty results, so each record
    domain owns its persistence model.
    An *environmental* failure raised inside
    ``provider_boundary`` (gateway drop, timeout) aborts the whole request —
    deliberately: providers here are complementary (each owns a window), not
    redundant failover, so a source that cannot even be reached fails closed
    rather than silently deferring to a lesser source. Add catch-and-continue
    only when a genuinely redundant provider exists, with a test pinning which
    semantic is wanted.

    The injected finalizer owns which physical dataset represents coverage:
    bars consolidate their record files, while sparse Custom Data consolidates
    its generic checked-interval records.
    """
    initial_missing = missing_intervals()
    if not initial_missing:
        return
    if provider is None:
        raise coverage_error(initial_missing)

    for missing in initial_missing:
        with provider_boundary(subject):
            served = provider(missing.start, missing.end)
        if not served.is_responsible:
            continue
        if served.oldest_verified is None:
            raise AssertionError("a verified provider answer needs a frontier")
        verified = missing.from_frontier(served.oldest_verified)
        if verified is None:
            continue
        records = tuple(
            served.records
            if select_records is None
            else select_records(served.records, verified)
        )
        commit(verified, records)

    remaining = missing_intervals()
    if remaining:
        raise coverage_error(remaining)
    finalize()
    if on_coverage_filled is not None:
        with provider_boundary(subject):
            on_coverage_filled()


__all__ = ["CoverageInterval", "ensure_coverage"]
