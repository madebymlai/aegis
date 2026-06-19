"""Trading calendars for Historical Store expected-bar coverage.

A :class:`TradingCalendar` selects the expected-bar calendar a Store Read or Pull
uses to decide which bars are required. It is a *required* input across the store
API (fail-closed) so coverage never silently assumes a venue. Calendar rules live
here only, so adding a venue is a one-place change.
"""

from __future__ import annotations

from enum import StrEnum

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    MO,
    TH,
    nearest_workday,
)
from pandas.tseries.offsets import BaseOffset


class TradingCalendar(StrEnum):
    """Named expected-bar calendar for Historical Store coverage."""

    XNYS = "xnys"  # US listed equities/ETFs; CME index futures approximation
    WEEKDAY = "weekday"  # Mon-Fri (FX); no exchange holidays
    CONTINUOUS = "continuous"  # 24/7 (crypto); every calendar day, Mon-Sun


class _XNYSHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year's Day", month=1, day=1, observance=nearest_workday),
        Holiday("Martin Luther King Jr. Day", month=1, day=1, offset=pd.DateOffset(weekday=MO(3))),
        Holiday("Washington's Birthday", month=2, day=1, offset=pd.DateOffset(weekday=MO(3))),
        GoodFriday,
        Holiday("Memorial Day", month=5, day=31, offset=pd.DateOffset(weekday=MO(-1))),
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        Holiday("Labor Day", month=9, day=1, offset=pd.DateOffset(weekday=MO(1))),
        Holiday("Thanksgiving Day", month=11, day=1, offset=pd.DateOffset(weekday=TH(4))),
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]


_BUSINESS_DAY: dict[TradingCalendar, BaseOffset] = {
    TradingCalendar.XNYS: pd.offsets.CustomBusinessDay(calendar=_XNYSHolidayCalendar()),
    TradingCalendar.WEEKDAY: pd.offsets.BDay(),
    TradingCalendar.CONTINUOUS: pd.offsets.Day(),
}

# Regular session span as (open, close) offsets from each active day's midnight.
# XNYS early-close half-days are handled by _session_offsets.
# WEEKDAY (FX) and CONTINUOUS (crypto) run the full calendar day.
_SESSION: dict[TradingCalendar, tuple[pd.Timedelta, pd.Timedelta]] = {
    TradingCalendar.XNYS: (pd.Timedelta(hours=9, minutes=30), pd.Timedelta(hours=16)),
    TradingCalendar.WEEKDAY: (pd.Timedelta(0), pd.Timedelta(days=1)),
    TradingCalendar.CONTINUOUS: (pd.Timedelta(0), pd.Timedelta(days=1)),
}
_XNYS_EARLY_CLOSE = pd.Timedelta(hours=13)


def as_trading_calendar(calendar: TradingCalendar | str) -> TradingCalendar:
    """Coerce a value to a :class:`TradingCalendar`, failing closed on unknowns."""
    try:
        return TradingCalendar(calendar)
    except ValueError as error:
        allowed = [cal.value for cal in TradingCalendar]
        raise ValueError(
            f"unsupported trading calendar {calendar!r}; expected one of {allowed}"
        ) from error


def business_day_offset(calendar: TradingCalendar | str) -> BaseOffset:
    """Resolve a calendar to its expected-bar business-day offset (fail-closed)."""
    return _BUSINESS_DAY[as_trading_calendar(calendar)]


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> pd.Timestamp:
    first = pd.Timestamp(year=year, month=month, day=1)
    days_until_weekday = (weekday - first.weekday()) % 7
    return first + pd.Timedelta(days=days_until_weekday + (occurrence - 1) * 7)


def _is_xnys_early_close(day: pd.Timestamp) -> bool:
    thanksgiving = _nth_weekday(day.year, 11, weekday=3, occurrence=4)
    normalized = day.normalize()
    return (
        normalized == thanksgiving + pd.Timedelta(days=1)
        or (normalized.month == 7 and normalized.day == 3)
        or (normalized.month == 12 and normalized.day == 24)
    )


def _session_offsets(
    calendar: TradingCalendar,
    day: pd.Timestamp,
) -> tuple[pd.Timedelta, pd.Timedelta]:
    open_off, close_off = _SESSION[calendar]
    if calendar == TradingCalendar.XNYS and _is_xnys_early_close(day):
        return open_off, _XNYS_EARLY_CLOSE
    return open_off, close_off


def intraday_session_bars(
    calendar: TradingCalendar | str,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DatetimeIndex:
    """Expected intraday bar timestamps for ``calendar`` over ``[start, end)``.

    Each active session day contributes ``date_range(open, close, freq=timeframe,
    inclusive="left")`` (a bar is stamped at its interval start), concatenated
    across active days and clipped to the half-open window. Timestamps are naive,
    in the calendar's local clock.
    """
    cal = as_trading_calendar(calendar)
    days = pd.date_range(start.normalize(), end.normalize(), freq=_BUSINESS_DAY[cal])
    bars = pd.DatetimeIndex([])
    for day in days:
        open_off, close_off = _session_offsets(cal, day)
        bars = bars.append(
            pd.date_range(day + open_off, day + close_off, freq=timeframe, inclusive="left")
        )
    return bars[(bars >= start) & (bars < end)]


__all__ = [
    "TradingCalendar",
    "as_trading_calendar",
    "business_day_offset",
    "intraday_session_bars",
]
