"""Pure Store Coverage rules."""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime import FuturesRef, ListedRef

from aegis_data.calendars import TradingCalendar
from aegis_data.store import FxPair, RawFuturesLeg
from aegis_data.store_coverage import (
    CoverageGap,
    HistoryWindow,
    StoreCoverage,
    StoreCoverageError,
)


def _window(
    *,
    timeframe: str = "1D",
    calendar: TradingCalendar = TradingCalendar.WEEKDAY,
    start: str = "2024-01-02",
    end: str = "2024-01-09",
) -> HistoryWindow:
    return HistoryWindow(timeframe=timeframe, calendar=calendar, start=start, end=end)


def test_native_gaps_group_contiguous_missing_expected_bars() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window()
    observed = pd.DataFrame(
        {"Close": [10.0, 13.0, 14.0]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-05", "2024-01-08"]),
    )

    gaps = StoreCoverage.for_native_bars(ref, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-01-03"), end=pd.Timestamp("2024-01-05")),
    )


def test_native_gaps_tolerate_futures_interior_missing_bars_only() -> None:
    ref = FuturesRef("GC", "GLBX.MDP3", roll_rule="calendar", adjustment="backward_ratio")
    window = _window(
        calendar=TradingCalendar.CME,
        start="2024-05-01",
        end="2024-06-01",
    )
    observed = pd.DataFrame(
        {"Close": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2024-05-02", "2024-05-31"]),
    )

    gaps = StoreCoverage.for_native_bars(ref, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-05-01"), end=pd.Timestamp("2024-05-02")),
    )


def test_native_gaps_tolerate_raw_futures_leg_interior_missing_bars_only() -> None:
    leg = RawFuturesLeg("GLBX.MDP3", "GCK4")
    window = _window(
        calendar=TradingCalendar.CONTINUOUS,
        start="2024-05-01",
        end="2024-05-06",
    )
    observed = pd.DataFrame(
        {"Close": [1.0, 2.0]},
        index=pd.DatetimeIndex(["2024-05-02", "2024-05-05"]),
    )

    gaps = StoreCoverage.for_native_bars(leg, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-05-01"), end=pd.Timestamp("2024-05-02")),
    )


def test_native_gaps_are_strict_for_listed_interior_missing_bars() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window()
    observed = pd.DataFrame(
        {"Close": [10.0, 12.0, 13.0, 14.0]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-04", "2024-01-05", "2024-01-08"]),
    )

    gaps = StoreCoverage.for_native_bars(ref, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-01-03"), end=pd.Timestamp("2024-01-04")),
    )


def test_history_window_expands_daily_business_days() -> None:
    window = _window(
        calendar=TradingCalendar.XNYS,
        start="2024-03-28",
        end="2024-04-02",
    )

    expected = window.expected_index()

    assert expected.equals(pd.DatetimeIndex(["2024-03-28", "2024-04-01"]))


def test_history_window_expands_intraday_session_bars_with_standard_early_close() -> None:
    window = _window(
        timeframe="15min",
        calendar=TradingCalendar.XNYS,
        start="2024-07-03 09:30",
        end="2024-07-03 16:00",
    )

    expected = window.expected_index()

    assert expected.equals(
        pd.DatetimeIndex(
            [
                "2024-07-03 09:30",
                "2024-07-03 09:45",
                "2024-07-03 10:00",
                "2024-07-03 10:15",
                "2024-07-03 10:30",
                "2024-07-03 10:45",
                "2024-07-03 11:00",
                "2024-07-03 11:15",
                "2024-07-03 11:30",
                "2024-07-03 11:45",
                "2024-07-03 12:00",
                "2024-07-03 12:15",
                "2024-07-03 12:30",
                "2024-07-03 12:45",
            ]
        )
    )


def test_empty_native_frame_is_fully_uncovered() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window()
    observed = pd.DataFrame(columns=["Close"], index=pd.DatetimeIndex([]))

    gaps = StoreCoverage.for_native_bars(ref, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-01-02"), end=pd.Timestamp("2024-01-09")),
    )


def test_missing_native_array_is_fully_uncovered() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window()
    observed = pd.DataFrame(
        {"Open": [10.0, 11.0, 12.0, 13.0, 14.0]},
        index=pd.DatetimeIndex(
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
        ),
    )

    gaps = StoreCoverage.for_native_bars(ref, arrays=("Close",)).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-01-02"), end=pd.Timestamp("2024-01-09")),
    )


def test_native_slice_returns_covered_history_window() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window(start="2024-01-03", end="2024-01-06")
    observed = pd.DataFrame(
        {
            "open": [9.0, 10.0, 11.0, 12.0],
            "close": [10.0, 11.0, 12.0, 13.0],
        },
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )

    sliced = StoreCoverage.for_native_bars(ref, arrays=("Close",)).slice(window, observed)

    pd.testing.assert_frame_equal(
        sliced,
        pd.DataFrame(
            {"Close": [11.0, 12.0, 13.0]},
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05"]),
        ),
    )


def test_native_assert_covered_accepts_complete_provider_frame() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window(start="2024-01-02", end="2024-01-05")
    observed = pd.DataFrame(
        {"Close": [10.0, 11.0, 12.0]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    StoreCoverage.for_native_bars(ref, arrays=("Close",)).assert_covered(window, observed)


def test_intraday_native_assert_covered_fails_on_missing_mid_session_bar() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window(
        timeframe="15min",
        calendar=TradingCalendar.XNYS,
        start="2024-01-02 09:30",
        end="2024-01-02 16:00",
    )
    observed = pd.DataFrame(
        {"Close": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0]},
        index=pd.DatetimeIndex(
            [
                "2024-01-02 09:30",
                "2024-01-02 09:45",
                "2024-01-02 10:00",
                "2024-01-02 10:15",
                "2024-01-02 10:30",
                "2024-01-02 10:45",
                "2024-01-02 11:15",
            ]
        ),
    )

    with pytest.raises(StoreCoverageError, match="11:00"):
        StoreCoverage.for_native_bars(ref, arrays=("Close",)).assert_covered(window, observed)


def test_intraday_native_assert_covered_accepts_xnys_standard_early_close() -> None:
    ref = ListedRef("BBG000B9XRY4")
    window = _window(
        timeframe="15min",
        calendar=TradingCalendar.XNYS,
        start="2024-11-29 09:30",
        end="2024-11-29 16:00",
    )
    observed = pd.DataFrame(
        {"Close": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0]},
        index=pd.DatetimeIndex(
            [
                "2024-11-29 09:30",
                "2024-11-29 09:45",
                "2024-11-29 10:00",
                "2024-11-29 10:15",
                "2024-11-29 10:30",
                "2024-11-29 10:45",
                "2024-11-29 11:00",
                "2024-11-29 11:15",
                "2024-11-29 11:30",
                "2024-11-29 11:45",
                "2024-11-29 12:00",
                "2024-11-29 12:15",
                "2024-11-29 12:30",
                "2024-11-29 12:45",
            ]
        ),
    )

    StoreCoverage.for_native_bars(ref, arrays=("Close",)).assert_covered(window, observed)


def test_fx_gaps_use_strict_rate_completeness() -> None:
    pair = FxPair("EUR", "USD")
    window = _window(start="2024-01-02", end="2024-01-05")
    observed = pd.DataFrame(
        {"rate": [1.10, None, 1.12]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    gaps = StoreCoverage.for_fx_rates(pair).gaps(window, observed)

    assert gaps == (
        CoverageGap(start=pd.Timestamp("2024-01-03"), end=pd.Timestamp("2024-01-04")),
    )


def test_fx_slice_fails_closed_on_missing_rate() -> None:
    pair = FxPair("EUR", "USD")
    window = _window(start="2024-01-02", end="2024-01-05")
    observed = pd.DataFrame(
        {"rate": [1.10, None, 1.12]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    with pytest.raises(StoreCoverageError, match="FX rate on 2024-01-03"):
        StoreCoverage.for_fx_rates(pair).slice(window, observed)


def test_fx_read_slice_fails_closed_when_history_is_absent() -> None:
    pair = FxPair("EUR", "USD")
    window = _window(start="2024-01-02", end="2024-01-05")
    observed = pd.DataFrame(columns=["rate"], index=pd.DatetimeIndex([]))

    with pytest.raises(StoreCoverageError, match="FX rate on 2024-01-02"):
        StoreCoverage.for_fx_rates(pair).slice(window, observed)


def test_fx_assert_covered_accepts_complete_provider_rates() -> None:
    pair = FxPair("EUR", "USD")
    window = _window(start="2024-01-02", end="2024-01-05")
    observed = pd.DataFrame(
        {"rate": [1.10, 1.11, 1.12]},
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    StoreCoverage.for_fx_rates(pair).assert_covered(window, observed)
