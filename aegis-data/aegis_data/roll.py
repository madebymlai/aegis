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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

DEFAULT_ROLL_LEAD_DAYS = 5


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
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
) -> FuturesChainSchedule:
    """Chain over ``[start, end]`` from *supplied* contracts.

    Rolls the front contract ``roll_lead_days`` business days before its last-trade
    date.  Eligible contracts and their expiries come from the caller (instrument
    definitions) — there is no hardcoded month cycle, so a monthly product rolls
    monthly and a serial/odd-cycle product rolls on whatever it actually lists.
    """
    _require_non_negative_roll_lead(roll_lead_days)
    in_window = _contracts_expiring_between(contracts, start, end)
    return FuturesChainSchedule(
        symbols=tuple(contract.symbol for contract in in_window),
        expiries=tuple(contract.last_trade for contract in in_window),
        roll_dates=tuple(_roll_date(contract, roll_lead_days) for contract in in_window[:-1]),
    )


def front_contract(
    contracts: Sequence[DatedContract],
    as_of: date,
    *,
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
) -> DatedContract | None:
    """Return the dated contract active on ``as_of`` under the expiry rule.

    This is the shared research/live selection seam: the caller supplies a provider
    contract calendar, and the rule switches on ``last_trade - roll_lead_days``
    business days.  ``None`` means the supplied calendar has no contract covering
    ``as_of``.
    """
    _require_non_negative_roll_lead(roll_lead_days)
    ordered = _contracts_by_expiry(contracts)
    if not ordered:
        return None

    active_schedule = roll_schedule(
        ordered, as_of, ordered[-1].last_trade, roll_lead_days=roll_lead_days
    )
    front_symbol = _front_symbol(active_schedule, as_of)
    if front_symbol is None:
        return None

    contract_by_symbol = {contract.symbol: contract for contract in ordered}
    return contract_by_symbol[front_symbol]


def assert_roll_agreement(
    root: str,
    research_contracts: Sequence[DatedContract],
    live_contracts: Sequence[DatedContract],
    start: date,
    end: date,
    *,
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
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
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
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


def _front_symbol(schedule: FuturesChainSchedule, as_of: date) -> str | None:
    if not schedule.symbols:
        return None
    for symbol, roll_date in zip(schedule.symbols, schedule.roll_dates, strict=False):
        if as_of < roll_date:
            return symbol
    return schedule.symbols[-1]


def _contracts_expiring_between(
    contracts: Sequence[DatedContract], start: date, end: date
) -> tuple[DatedContract, ...]:
    return tuple(
        contract
        for contract in _contracts_by_expiry(contracts)
        if start <= contract.last_trade <= end
    )


def _contracts_by_expiry(contracts: Sequence[DatedContract]) -> tuple[DatedContract, ...]:
    return tuple(sorted(contracts, key=lambda contract: contract.last_trade))


def _roll_date(contract: DatedContract, roll_lead_days: int) -> date:
    return _minus_business_days(contract.last_trade, roll_lead_days)


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
    "DEFAULT_ROLL_LEAD_DAYS",
    "DatedContract",
    "FuturesChainSchedule",
    "RollAgreement",
    "RollAgreementError",
    "assert_roll_agreement",
    "assert_universe_roll_agreement",
    "front_contract",
    "roll_schedule",
]
