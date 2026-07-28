"""Shared coverage traversal behavior."""

from contextlib import contextmanager

import pandas as pd

from aegis_data._ensure_coverage import (
    CoverageInterval,
    ServedRecords,
    ensure_coverage,
)


def test_ensure_coverage_leaves_persistence_to_the_caller() -> None:
    missing = [CoverageInterval(10, 20)]
    committed: list[tuple[CoverageInterval, tuple[str, ...]]] = []
    finalized: list[bool] = []

    @contextmanager
    def provider_boundary(_subject: str):
        yield

    def commit(
        interval: CoverageInterval,
        records: tuple[str, ...],
    ) -> None:
        committed.append((interval, records))
        missing.clear()

    ensure_coverage(
        subject="fixture",
        fetchers=(
            lambda _start, _end: ServedRecords(
                ("record",),
                pd.Timestamp(10, tz="UTC"),
            ),
        ),
        missing_intervals=lambda: list(missing),
        commit=commit,
        finalize=lambda: finalized.append(True),
        coverage_error=lambda intervals: AssertionError(intervals),
        provider_boundary=provider_boundary,
    )

    assert committed == [(CoverageInterval(10, 20), ("record",))]
    assert finalized == [True]
