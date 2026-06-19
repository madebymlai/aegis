"""Pure futures roll schedule (aegis-rd-a7h).

A continuous back-adjusted series needs to know which dated contracts make up the chain
and when the position rolls from one to the next.  The rule is expiry-driven: roll a
fixed number of business days before each contract's last-trade date.  Eligible contracts
are *supplied* (from instrument definitions), so there is no hardcoded month cycle — a
monthly product rolls monthly and an odd-cycle product rolls on whatever it lists.
"""

from __future__ import annotations

from datetime import date

from aegis_data.roll import DatedContract, roll_schedule


def test_monthly_contracts_roll_monthly() -> None:
    # Crude (CL) lists every month; the chain must roll through ALL of them, not a
    # quarterly subset.  Contracts are supplied (from instrument definitions), so the
    # roll has no hardcoded month cycle.
    contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
        DatedContract("CLU6", date(2026, 8, 20)),
        DatedContract("CLV6", date(2026, 9, 22)),
    ]
    sched = roll_schedule(contracts, date(2026, 6, 1), date(2026, 9, 30), roll_lead_days=5)

    assert sched.symbols == ("CLN6", "CLQ6", "CLU6", "CLV6")


def test_roll_date_is_business_days_before_last_trade() -> None:
    # Last-trade Monday 2026-06-22; 3 business days before skips the weekend → Wed 06-17.
    sched = roll_schedule(
        [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        date(2026, 6, 1),
        date(2026, 7, 31),
        roll_lead_days=3,
    )
    assert sched.roll_dates == (date(2026, 6, 17),)


def test_arbitrary_cycle_rolls_on_supplied_months() -> None:
    # Corn (ZC) lists H/K/N/U/Z — not the {H,M,U,Z} quarterly cycle.  The chain rolls on
    # exactly the supplied contracts, with no hardcoded month assumption.
    contracts = [
        DatedContract("ZCH6", date(2026, 3, 13)),
        DatedContract("ZCK6", date(2026, 5, 14)),
        DatedContract("ZCN6", date(2026, 7, 14)),
    ]
    sched = roll_schedule(contracts, date(2026, 1, 1), date(2026, 12, 31), roll_lead_days=5)
    assert sched.symbols == ("ZCH6", "ZCK6", "ZCN6")


def test_contracts_expiring_outside_window_are_excluded() -> None:
    contracts = [
        DatedContract("CLM6", date(2026, 5, 20)),  # expires before start → excluded
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
        DatedContract("CLU6", date(2026, 8, 20)),  # expires after end → excluded
    ]
    sched = roll_schedule(contracts, date(2026, 6, 1), date(2026, 7, 31), roll_lead_days=5)

    assert sched.symbols == ("CLN6", "CLQ6")
    assert list(sched.roll_dates) == sorted(sched.roll_dates)  # chronological


def test_quarterly_product_still_rolls_quarterly() -> None:
    # A quarterly product is just the case where only H/M/U/Z contracts are supplied —
    # quarterly support is preserved, not special-cased away.
    contracts = [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),
    ]
    sched = roll_schedule(contracts, date(2024, 1, 1), date(2024, 12, 31), roll_lead_days=5)

    assert sched.symbols == ("ESH4", "ESM4", "ESU4", "ESZ4")
    assert sched.roll_dates[0] == date(2024, 3, 8)  # 5 business days before Fri 2024-03-15


def test_unsorted_contracts_produce_a_chronological_chain() -> None:
    contracts = [
        DatedContract("CLU6", date(2026, 8, 20)),
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
    ]
    sched = roll_schedule(contracts, date(2026, 6, 1), date(2026, 9, 30), roll_lead_days=5)

    assert sched.symbols == ("CLN6", "CLQ6", "CLU6")
    assert sched.expiries == (date(2026, 6, 22), date(2026, 7, 21), date(2026, 8, 20))


def test_single_contract_has_no_roll() -> None:
    sched = roll_schedule(
        [DatedContract("CLN6", date(2026, 6, 22))],
        date(2026, 6, 1),
        date(2026, 7, 1),
        roll_lead_days=5,
    )
    assert sched.symbols == ("CLN6",)
    assert sched.roll_dates == ()


def test_no_contracts_in_window_is_an_empty_schedule() -> None:
    # Define errors out of existence: an out-of-range window yields an empty schedule, not a raise.
    sched = roll_schedule(
        [DatedContract("CLN6", date(2026, 6, 22))],
        date(2027, 1, 1),
        date(2027, 12, 31),
        roll_lead_days=5,
    )
    assert sched.symbols == ()
    assert sched.expiries == ()
    assert sched.roll_dates == ()


def test_roll_lead_zero_rolls_on_the_last_trade_date() -> None:
    # Databento `.c.0` calendar continuous rolls ~at expiry; lead 0 reproduces that anchor.
    sched = roll_schedule(
        [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        date(2026, 6, 1),
        date(2026, 7, 31),
        roll_lead_days=0,
    )
    assert sched.roll_dates == (date(2026, 6, 22),)
