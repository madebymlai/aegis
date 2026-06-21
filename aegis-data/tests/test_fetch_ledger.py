"""Pure Fetch Ledger interval arithmetic."""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_data.fetch_ledger import FetchedInterval, FetchLedger
from aegis_data.store_coverage import CoverageGap


def _interval(start: str, end: str) -> FetchedInterval:
    return FetchedInterval(start=pd.Timestamp(start), end=pd.Timestamp(end))


def test_fetch_ledger_empty_returns_whole_window_gap() -> None:
    ledger = FetchLedger.of(())
    window = _interval("2024-01-01", "2024-01-05")

    gaps = ledger.gaps(window)

    assert gaps == (CoverageGap(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-05")),)


def test_fetch_ledger_full_cover_returns_no_gaps() -> None:
    ledger = FetchLedger.of((_interval("2024-01-01", "2024-01-05"),))
    window = _interval("2024-01-01", "2024-01-05")

    gaps = ledger.gaps(window)

    assert gaps == ()


def test_fetch_ledger_reports_left_interior_and_right_gaps() -> None:
    ledger = FetchLedger.of(
        (
            _interval("2024-01-02", "2024-01-03"),
            _interval("2024-01-04", "2024-01-05"),
        )
    )
    window = _interval("2024-01-01", "2024-01-06")

    gaps = ledger.gaps(window)

    assert gaps == (
        CoverageGap(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")),
        CoverageGap(pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04")),
        CoverageGap(pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-06")),
    )


def test_fetch_ledger_coalesces_touching_and_overlapping_intervals() -> None:
    ledger = FetchLedger.of(
        (
            _interval("2024-01-01", "2024-01-03"),
            _interval("2024-01-03", "2024-01-04"),
            _interval("2024-01-02", "2024-01-05"),
        )
    )
    window = _interval("2024-01-01", "2024-01-05")

    gaps = ledger.gaps(window)

    assert gaps == ()


def test_fetch_ledger_ignores_intervals_outside_the_requested_window() -> None:
    ledger = FetchLedger.of(
        (
            _interval("2023-12-01", "2023-12-02"),
            _interval("2024-01-02", "2024-01-03"),
            _interval("2024-01-10", "2024-01-11"),
        )
    )
    window = _interval("2024-01-01", "2024-01-05")

    gaps = ledger.gaps(window)

    assert gaps == (
        CoverageGap(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")),
        CoverageGap(pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")),
    )


def test_fetched_interval_rejects_degenerate_window() -> None:
    with pytest.raises(ValueError, match="end must be after start"):
        _interval("2024-01-02", "2024-01-02")
