"""Pure futures roll schedule (calendar rule).

The roll is deterministic from the contract calendar: roll the front contract a fixed
number of business days before its last-trade date.  Eligible contracts and their
expiries are *supplied* by the caller (instrument definitions) — there is no hardcoded
month cycle, so a monthly product rolls monthly and a serial/odd-cycle product rolls on
whatever it actually lists.  This names the dated-contract chain over a date range and
the roll date between consecutive contracts — the schedule the per-contract source
fetches against and the back-adjustment transform stitches on.

Pure: no I/O, no provider.  Holiday calendars are out of scope (business-day = Mon-Fri).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta


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


@dataclass(frozen=True)
class DatedContract:
    """A dated futures contract and its last-trade date, as named by an instrument
    definition (Databento at research, the IBKR chain at live)."""

    symbol: str
    last_trade: date


def roll_schedule(
    contracts: Sequence[DatedContract], start: date, end: date, *, roll_lead_days: int = 5
) -> FuturesChainSchedule:
    """Chain over ``[start, end]`` from *supplied* contracts.

    Rolls the front contract ``roll_lead_days`` business days before its last-trade
    date.  Eligible contracts and their expiries come from the caller (instrument
    definitions) — there is no hardcoded month cycle, so a monthly product rolls
    monthly and a serial/odd-cycle product rolls on whatever it actually lists.
    """
    in_window = [
        c for c in sorted(contracts, key=lambda c: c.last_trade) if start <= c.last_trade <= end
    ]
    return FuturesChainSchedule(
        symbols=tuple(c.symbol for c in in_window),
        expiries=tuple(c.last_trade for c in in_window),
        roll_dates=tuple(_minus_business_days(c.last_trade, roll_lead_days) for c in in_window[:-1]),
    )


def _minus_business_days(day: date, count: int) -> date:
    current = day
    remaining = count
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


__all__ = ["DatedContract", "FuturesChainSchedule", "roll_schedule"]
