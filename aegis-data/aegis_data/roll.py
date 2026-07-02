"""Pure futures roll schedule (calendar rule).

The roll is deterministic from the contract calendar: roll the front contract a fixed
number of business days before its last-trade date.  Eligible contracts and their
expiries are *supplied* by the caller (instrument definitions) — there is no hardcoded
month cycle, so a monthly product rolls monthly and a serial/odd-cycle product rolls on
whatever it actually lists.  This names the dated-contract chain over a date range and
the roll date between consecutive contracts — the schedule the per-contract source
fetches against and the roll-transition table is built from.

Pure: no I/O, no provider.  Holiday calendars are out of scope (business-day = Mon-Fri).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

# Roll about one trading week before last-trade: clears first-notice/delivery and
# the liquidity migration to the back contract.  Not an operator knob — the lead is
# derived from the bar cadence (see ``roll_lead_days_for_cadence``).
ROLL_LIQUIDITY_BUFFER_DAYS = 5

_ONE_BUSINESS_DAY = timedelta(days=1)


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
    definition in the Nautilus catalog (IBKR-seeded)."""

    symbol: str
    last_trade: date


@dataclass(frozen=True)
class RollAgreement:
    """A root whose research and live contract calendars produce one roll schedule."""

    root: str
    symbols: tuple[str, ...]
    expiries: tuple[date, ...]
    roll_dates: tuple[date, ...]


class RollAgreementError(ValueError):
    """Research and live contract calendars disagree for a futures roll rule."""


def roll_schedule(
    contracts: Sequence[DatedContract],
    start: date,
    end: date,
    *,
    roll_lead_days: int,
) -> FuturesChainSchedule:
    """Chain over ``[start, end]`` from *supplied* contracts.

    Rolls the front contract ``roll_lead_days`` business days before its last-trade
    date.  Eligible contracts and their expiries come from the caller (instrument
    definitions) — there is no hardcoded month cycle, so a monthly product rolls
    monthly and a serial/odd-cycle product rolls on whatever it actually lists.
    """
    _require_non_negative_roll_lead(roll_lead_days)
    in_window = _contracts_front_between(
        _contracts_by_expiry(contracts), start, end, roll_lead_days
    )
    return FuturesChainSchedule(
        symbols=tuple(contract.symbol for contract in in_window),
        expiries=tuple(contract.last_trade for contract in in_window),
        roll_dates=tuple(_roll_date(contract, roll_lead_days) for contract in in_window[:-1]),
    )


def front_contract(
    contracts: Sequence[DatedContract],
    as_of: date,
    *,
    roll_lead_days: int,
) -> DatedContract | None:
    """Return the dated contract active on ``as_of`` under the expiry rule.

    This is the shared research/live selection seam: the caller supplies a provider
    contract calendar, and the rule switches on ``last_trade - roll_lead_days``
    business days.  ``None`` means the supplied calendar has no contract covering
    ``as_of``.
    """
    _require_non_negative_roll_lead(roll_lead_days)
    ordered = _contracts_by_expiry(contracts)
    index = _front_index(ordered, as_of, roll_lead_days)
    return None if index is None else ordered[index]


def roll_date(contract: DatedContract, *, roll_lead_days: int) -> date:
    """The calendar roll date for ``contract`` — ``roll_lead_days`` business days before its last
    trade.  The chain switches off ``contract`` onto its successor here under the calendar rule (the
    seam the liquidity cap may move earlier)."""
    _require_non_negative_roll_lead(roll_lead_days)
    return _roll_date(contract, roll_lead_days)


def assert_roll_agreement(
    root: str,
    research_contracts: Sequence[DatedContract],
    live_contracts: Sequence[DatedContract],
    start: date,
    end: date,
    *,
    roll_lead_days: int,
) -> RollAgreement:
    """Assert one root's research and live calendars produce the same schedule."""
    research = roll_schedule(
        research_contracts, start, end, roll_lead_days=roll_lead_days
    )
    live = roll_schedule(live_contracts, start, end, roll_lead_days=roll_lead_days)
    if research != live:
        raise RollAgreementError(
            f"roll schedule mismatch for {root}: research={research!r} live={live!r}"
        )
    return RollAgreement(
        root=root,
        symbols=research.symbols,
        expiries=research.expiries,
        roll_dates=research.roll_dates,
    )


def assert_universe_roll_agreement(
    roots: Sequence[str],
    research_contracts_by_root: Mapping[str, Sequence[DatedContract]],
    live_contracts_by_root: Mapping[str, Sequence[DatedContract]],
    start: date,
    end: date,
    *,
    roll_lead_days: int,
) -> tuple[RollAgreement, ...]:
    """Assert roll-schedule parity for every root in a futures universe."""
    return tuple(
        assert_roll_agreement(
            root,
            research_contracts_by_root[root],
            live_contracts_by_root[root],
            start,
            end,
            roll_lead_days=roll_lead_days,
        )
        for root in roots
    )


def _front_index(
    ordered: Sequence[DatedContract], as_of: date, roll_lead_days: int
) -> int | None:
    """Index (into expiry-ordered contracts) of the one front on ``as_of``.

    The front contract is the earliest-expiring one that has not yet rolled off:
    the first whose roll date is still ahead of ``as_of``.  Once ``as_of`` is past
    every roll date but on/before the back contract's last trade, that back contract
    is front.  ``None`` means ``as_of`` is past the last contract's last trade — no
    supplied contract covers it.
    """
    if not ordered or as_of > ordered[-1].last_trade:
        return None
    for index, contract in enumerate(ordered):
        if as_of < _roll_date(contract, roll_lead_days):
            return index
    return len(ordered) - 1


def _contracts_front_between(
    ordered: Sequence[DatedContract], start: date, end: date, roll_lead_days: int
) -> tuple[DatedContract, ...]:
    """Every contract that is front at some point in ``[start, end]``.

    The front contract advances monotonically with ``as_of``, so this is the
    contiguous run from the contract front at ``start`` through the one front at
    ``end`` — inclusive of the front-at-``end`` contract even when its last trade
    falls *after* ``end`` (it is the only leg covering ``[last expiry, end]``).  An
    ``end`` past every contract runs through the back contract; a ``start`` past
    every contract yields the empty chain (aegis-rd-vv6).
    """
    first = _front_index(ordered, start, roll_lead_days)
    if first is None:
        return ()
    last = _front_index(ordered, end, roll_lead_days)
    last = len(ordered) - 1 if last is None else last
    return tuple(ordered[first : last + 1])


def _contracts_by_expiry(contracts: Sequence[DatedContract]) -> tuple[DatedContract, ...]:
    return tuple(sorted(contracts, key=lambda contract: contract.last_trade))


def _roll_date(contract: DatedContract, roll_lead_days: int) -> date:
    return _minus_business_days(contract.last_trade, roll_lead_days)


def roll_lead_days_for_cadence(bar_cadence: timedelta) -> int:
    """Business-day roll lead derived from the book's bar cadence — no operator knob.

    Rolls about one trading week before last-trade (clearing first-notice/delivery and
    the liquidity migration to the back contract), but never later than the cadence
    safety floor — two bars, the one acted on plus the one-bar next-close execution
    latency (ADR-0001).  So a coarse timeframe rolls earlier (weekly -> 14), an intraday
    one keeps the week buffer (-> 5), and research and live derive the same lead from
    the cadence they already share.
    """
    safety_floor = max(1, math.ceil(2 * bar_cadence / _ONE_BUSINESS_DAY))
    return max(ROLL_LIQUIDITY_BUFFER_DAYS, safety_floor)


def _require_non_negative_roll_lead(roll_lead_days: int) -> None:
    if roll_lead_days < 0:
        raise ValueError("roll_lead_days must be non-negative")


def _minus_business_days(day: date, count: int) -> date:
    current = day
    remaining = count
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


__all__ = [
    "ROLL_LIQUIDITY_BUFFER_DAYS",
    "DatedContract",
    "FuturesChainSchedule",
    "RollAgreement",
    "RollAgreementError",
    "assert_roll_agreement",
    "assert_universe_roll_agreement",
    "front_contract",
    "roll_date",
    "roll_lead_days_for_cadence",
    "roll_schedule",
]
