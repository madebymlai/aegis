"""Trading calendars for Historical Store coverage (aegis-data)."""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_data.calendars import (
    TradingCalendar,
    as_trading_calendar,
    business_day_offset,
    intraday_session_bars,
)


def test_weekday_calendar_expects_a_us_holiday_that_xnys_skips() -> None:
    # MLK Day 2024-01-15 (Mon) is a weekday but an XNYS holiday.
    weekday = pd.date_range(
        "2024-01-12", "2024-01-17", freq=business_day_offset(TradingCalendar.WEEKDAY)
    )
    xnys = pd.date_range(
        "2024-01-12", "2024-01-17", freq=business_day_offset(TradingCalendar.XNYS)
    )
    mlk = pd.Timestamp("2024-01-15")

    assert mlk in weekday
    assert mlk not in xnys


def test_continuous_calendar_expects_a_weekend_day_that_weekday_skips() -> None:
    # 2024-01-13 (Sat) / 2024-01-14 (Sun): a 24/7 market trades; a Mon-Fri market does not.
    continuous = pd.date_range(
        "2024-01-12", "2024-01-15", freq=business_day_offset(TradingCalendar.CONTINUOUS)
    )
    weekday = pd.date_range(
        "2024-01-12", "2024-01-15", freq=business_day_offset(TradingCalendar.WEEKDAY)
    )
    saturday = pd.Timestamp("2024-01-13")
    sunday = pd.Timestamp("2024-01-14")

    assert saturday in continuous
    assert sunday in continuous
    assert saturday not in weekday
    assert sunday not in weekday


def test_intraday_session_bars_xnys_uses_regular_rth_window() -> None:
    bars = intraday_session_bars(
        TradingCalendar.XNYS,
        "15min",
        pd.Timestamp("2024-01-02 00:00"),
        pd.Timestamp("2024-01-03 00:00"),
    )
    assert bars[0] == pd.Timestamp("2024-01-02 09:30")
    assert bars[-1] == pd.Timestamp("2024-01-02 15:45")  # 16:00 close excluded (interval start)
    assert len(bars) == 26


def test_intraday_session_bars_continuous_covers_a_weekend_that_weekday_skips() -> None:
    saturday = pd.Timestamp("2024-01-13 00:00")
    sunday = pd.Timestamp("2024-01-14 00:00")
    continuous = intraday_session_bars(TradingCalendar.CONTINUOUS, "1h", saturday, sunday)
    weekday = intraday_session_bars(TradingCalendar.WEEKDAY, "1h", saturday, sunday)

    assert len(continuous) == 24  # full 24h on a Saturday
    assert len(weekday) == 0  # Saturday is not a WEEKDAY session


def test_unknown_calendar_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported trading calendar"):
        as_trading_calendar("lse")
    with pytest.raises(ValueError, match="unsupported trading calendar"):
        business_day_offset("lse")
