"""Pure futures roll schedule (calendar rule).

For a quarterly index future (H/M/U/Z, expiry on the third Friday) the calendar
roll rule is deterministic: roll a fixed number of business days before each
contract's expiry.  This names the dated-contract chain over a date range and
the roll date between consecutive contracts — the schedule the per-contract
source fetches against and the back-adjustment transform stitches on.

Pure: no I/O, no provider.  Holiday calendars are out of scope (business-day =
Mon-Fri); the calendar rule is an approximation by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# CME quarterly cycle: March/June/September/December → H/M/U/Z.
_QUARTERLY_MONTHS: dict[int, str] = {3: "H", 6: "M", 9: "U", 12: "Z"}
_FRIDAY = 4  # date.weekday(): Monday=0 … Sunday=6


@dataclass(frozen=True)
class FuturesChainSchedule:
    """The dated-contract chain for a future over a date range.

    ``symbols`` are chronological (front→back); ``expiries`` is aligned 1:1;
    ``roll_dates`` has one entry per seam (``len(symbols) - 1``): the date the
    chain switches off ``symbols[i]`` onto ``symbols[i + 1]``.
    """

    symbols: tuple[str, ...]
    expiries: tuple[date, ...]
    roll_dates: tuple[date, ...]


def quarterly_roll_schedule(
    root: str, start: date, end: date, *, roll_lead_days: int = 5
) -> FuturesChainSchedule:
    """Quarterly chain whose contracts expire within ``[start, end]``."""
    symbols: list[str] = []
    expiries: list[date] = []
    for year in range(start.year, end.year + 1):
        for month, code in sorted(_QUARTERLY_MONTHS.items()):
            expiry = _third_friday(year, month)
            if expiry < start or expiry > end:
                continue
            symbols.append(f"{root}{code}{year % 10}")
            expiries.append(expiry)
    roll_dates = tuple(
        _minus_business_days(expiry, roll_lead_days) for expiry in expiries[:-1]
    )
    return FuturesChainSchedule(
        symbols=tuple(symbols), expiries=tuple(expiries), roll_dates=roll_dates
    )


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(_FRIDAY - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def _minus_business_days(day: date, count: int) -> date:
    current = day
    remaining = count
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


__all__ = ["FuturesChainSchedule", "quarterly_roll_schedule"]
