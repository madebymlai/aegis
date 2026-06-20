"""Pure futures roll schedule (aegis-rd-a7h).

A continuous back-adjusted series needs to know which dated contracts make up the chain
and when the position rolls from one to the next.  The rule is expiry-driven: roll a
fixed number of business days before each contract's last-trade date.  Eligible contracts
are *supplied* (from instrument definitions), so there is no hardcoded month cycle — a
monthly product rolls monthly and an odd-cycle product rolls on whatever it lists.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from aegis_data.roll import (
    DatedContract,
    RollAgreementError,
    assert_roll_agreement,
    assert_universe_roll_agreement,
    front_contract,
    roll_lead_days_for_cadence,
    roll_schedule,
)


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


def test_leading_edge_rolled_off_contract_is_excluded_but_front_at_end_is_kept() -> None:
    # Selection spans every contract front during the window.  A contract that rolled
    # off before start (never front in the window) is excluded; the contract front at
    # end is kept even though it expires after end — it is the only leg covering
    # [last expiry, end] (aegis-rd-vv6).
    contracts = [
        DatedContract("CLM6", date(2026, 5, 20)),  # rolled off before start → excluded
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
        DatedContract("CLU6", date(2026, 8, 20)),  # front at end (expires after it) → kept
    ]
    sched = roll_schedule(contracts, date(2026, 6, 1), date(2026, 7, 31), roll_lead_days=5)

    assert sched.symbols == ("CLN6", "CLQ6", "CLU6")
    assert list(sched.roll_dates) == sorted(sched.roll_dates)  # chronological


def test_front_at_end_contract_is_in_the_chain_even_though_it_expires_after_end() -> None:
    # aegis-rd-vv6: the chain must span every contract that is front at some point in
    # [start, end] — including the one front *at* end, whose last trade falls after end.
    # Otherwise no leg covers [last expiry, end] and a store pull aborts at the edge.
    contracts = [
        DatedContract("ESH4", date(2024, 3, 15)),
        DatedContract("ESM4", date(2024, 6, 21)),
        DatedContract("ESU4", date(2024, 9, 20)),
        DatedContract("ESZ4", date(2024, 12, 20)),  # front at end; expires after it
    ]
    # end 2024-10-01: past ESU4's expiry, mid-ESZ4 life.
    sched = roll_schedule(contracts, date(2024, 1, 2), date(2024, 10, 1), roll_lead_days=5)

    assert sched.symbols == ("ESH4", "ESM4", "ESU4", "ESZ4")


def test_window_spanning_no_expiry_yields_the_single_front_contract() -> None:
    # aegis-rd-vv6 (leading-edge symmetry): a short window entirely inside one contract's
    # life spans no expiry.  The old expiry-window filter returned an empty chain; the
    # selection must instead name the contract that is front throughout the window.
    contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
    ]
    # [6/25, 7/5]: after CLN6's roll (6/15), before CLQ6's (7/14) → CLQ6 front throughout.
    sched = roll_schedule(contracts, date(2026, 6, 25), date(2026, 7, 5), roll_lead_days=5)

    assert sched.symbols == ("CLQ6",)
    assert sched.roll_dates == ()


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


def test_front_contract_uses_the_shared_expiry_driven_roll_rule() -> None:
    contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
        DatedContract("CLU6", date(2026, 8, 20)),
    ]

    before_roll = front_contract(contracts, date(2026, 6, 12), roll_lead_days=5)
    on_roll = front_contract(contracts, date(2026, 6, 15), roll_lead_days=5)

    assert before_roll == DatedContract("CLN6", date(2026, 6, 22))
    assert on_roll == DatedContract("CLQ6", date(2026, 7, 21))


def test_roll_agreement_harness_returns_the_shared_schedule() -> None:
    research_contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
    ]
    live_contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
    ]

    agreement = assert_roll_agreement(
        "CL",
        research_contracts,
        live_contracts,
        date(2026, 6, 1),
        date(2026, 7, 31),
        roll_lead_days=5,
    )

    assert agreement.root == "CL"
    assert agreement.symbols == ("CLN6", "CLQ6")
    assert agreement.roll_dates == (date(2026, 6, 15),)


def test_roll_agreement_harness_fails_closed_on_live_research_mismatch() -> None:
    research_contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
    ]
    live_contracts = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLU6", date(2026, 8, 20)),
    ]

    with pytest.raises(RollAgreementError, match="CL"):
        assert_roll_agreement(
            "CL",
            research_contracts,
            live_contracts,
            date(2026, 6, 1),
            date(2026, 8, 31),
            roll_lead_days=5,
        )


@pytest.mark.parametrize(
    ("bar_cadence", "expected_lead"),
    [
        (timedelta(hours=1), 5),   # intraday: 2h span < buffer, the one-week buffer governs
        (timedelta(days=1), 5),    # daily: lands on the one-week liquidity buffer
        (timedelta(days=3), 6),    # crossover: two 3-day bars (6) just exceed the buffer
        (timedelta(weeks=1), 14),  # weekly: 14-day span, the cadence safety floor wins
    ],
)
def test_roll_lead_is_derived_from_bar_cadence(bar_cadence, expected_lead) -> None:
    # The lead is derived from the bar cadence, never configured: roll ~a trading week
    # before last-trade (clearing first-notice + liquidity migration), floored at the
    # cadence safety minimum (two bars: act + next-close).
    assert roll_lead_days_for_cadence(bar_cadence) == expected_lead


def test_universe_roll_agreement_returns_one_schedule_per_root() -> None:
    # Same real CME contracts on both substrates (Databento defs vs the IBKR chain)
    # => identical last-trade dates => identical schedules for the shared lead.
    research = {
        "CL": [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        "GC": [DatedContract("GCM6", date(2026, 6, 25)), DatedContract("GCQ6", date(2026, 8, 27))],
    }
    live = {
        "CL": [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        "GC": [DatedContract("GCM6", date(2026, 6, 25)), DatedContract("GCQ6", date(2026, 8, 27))],
    }

    agreements = assert_universe_roll_agreement(
        ("CL", "GC"), research, live, date(2026, 6, 1), date(2026, 8, 31), roll_lead_days=5
    )

    assert tuple(a.root for a in agreements) == ("CL", "GC")
    assert agreements[0].symbols == ("CLN6", "CLQ6")
    assert agreements[1].symbols == ("GCM6", "GCQ6")


def test_universe_roll_agreement_fails_closed_naming_the_divergent_root() -> None:
    # CL agrees; GC's live chain lists a different back contract than research.
    research = {
        "CL": [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        "GC": [DatedContract("GCM6", date(2026, 6, 25)), DatedContract("GCQ6", date(2026, 8, 27))],
    }
    live = {
        "CL": [DatedContract("CLN6", date(2026, 6, 22)), DatedContract("CLQ6", date(2026, 7, 21))],
        "GC": [DatedContract("GCM6", date(2026, 6, 25)), DatedContract("GCV6", date(2026, 9, 28))],
    }

    with pytest.raises(RollAgreementError, match="GC"):
        assert_universe_roll_agreement(
            ("CL", "GC"), research, live, date(2026, 6, 1), date(2026, 9, 30), roll_lead_days=5
        )
