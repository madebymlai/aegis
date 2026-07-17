"""One internal Ensure Coverage engine for every catalog record type."""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import pandas as pd


RecordT = TypeVar("RecordT")
MissingIntervals = Callable[[], list[tuple[int, int]]]
CoverageError = Callable[[Sequence[tuple[int, int]]], Exception]
ProviderBoundary = Callable[[str], AbstractContextManager[None]]
EmptyIntervalWriter = Callable[[int, int], None]
CoverageSuccess = Callable[[], None]


@dataclass(frozen=True)
class FetchedRecords(Generic[RecordT]):
    """One provider's records and oldest source-verified instant."""

    records: tuple[RecordT, ...]
    served_from: pd.Timestamp


RecordFetcher = Callable[[pd.Timestamp, pd.Timestamp], FetchedRecords[RecordT]]


def ensure_coverage(
    catalog: Any,
    *,
    data_cls: type,
    identifier: str,
    subject: str,
    fetchers: Sequence[RecordFetcher[Any]],
    missing_intervals: MissingIntervals,
    coverage_error: CoverageError,
    provider_boundary: ProviderBoundary,
    empty_interval_writer: EmptyIntervalWriter | None = None,
    on_coverage_filled: CoverageSuccess | None = None,
    consolidate_start_ns: int | None = None,
    consolidate_end_ns: int | None = None,
) -> None:
    """Fill, consolidate, and re-verify one requested catalog window."""
    initial_missing = missing_intervals()
    if not initial_missing:
        return
    if not fetchers:
        raise coverage_error(initial_missing)

    wrote_records = False
    for fetch in fetchers:
        for start_ns, end_ns in missing_intervals():
            with provider_boundary(subject):
                served = fetch(
                    pd.Timestamp(start_ns, tz="UTC"),
                    pd.Timestamp(end_ns, tz="UTC"),
                )
            served_from_ns = max(start_ns, served.served_from.value)
            if served_from_ns > end_ns:
                continue
            if served.records:
                catalog.write_data(
                    list(served.records),
                    data_cls=data_cls,
                    identifier=identifier,
                    start=served_from_ns,
                    end=end_ns,
                )
                wrote_records = True
            elif empty_interval_writer is not None:
                empty_interval_writer(served_from_ns, end_ns)

    if wrote_records:
        catalog.consolidate_data(
            data_cls,
            identifier=identifier,
            start=consolidate_start_ns,
            end=consolidate_end_ns,
            deduplicate=True,
        )
    remaining = missing_intervals()
    if remaining:
        raise coverage_error(remaining)
    if on_coverage_filled is not None:
        with provider_boundary(subject):
            on_coverage_filled()


__all__ = ["FetchedRecords", "ensure_coverage"]
