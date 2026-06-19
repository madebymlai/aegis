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


__all__ = ["TradingCalendar", "as_trading_calendar", "business_day_offset"]
