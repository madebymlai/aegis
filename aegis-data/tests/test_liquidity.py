"""Volume liquidity-leadership eligibility — the Liquid Cycle (aegis-rd-3yu).

A continuous futures series should hold only the dated contracts a desk actually
trades and skip thin Serial Months.  ``liquid_cycle`` reads that membership from
data: a contract is eligible iff it is *ever* the Liquidity Leader (highest daily
volume among the contemporaneously-live contracts of its root) over its own life,
judged on volume smoothed over the roll-lead window.  Pure over a candidate set and
its volumes, so it is tested without I/O (prior art: the pure tests in test_roll.py).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

import pytest

from aegis_data.liquidity import (
    assert_liquid_cycle_agreement,
    liquid_cycle,
    liquid_cycle_causal,
)
from aegis_data.roll import DatedContract, RollAgreementError


def _flat_volume(start: date, end: date, value: float) -> pd.Series:
    index = pd.bdate_range(start, end)
    return pd.Series([value] * len(index), index=index, dtype="float64")


def test_serial_months_are_excluded_from_the_liquid_cycle() -> None:
    # GC over May–Aug: the May (GCK4) and July (GCN4) serials trade thinly beside the
    # liquid June (GCM4) and August (GCQ4) contracts, so they never lead and are out.
    candidates = [
        DatedContract("GCK4", date(2024, 5, 28)),
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCN4", date(2024, 7, 29)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    volume = {
        "GCK4": _flat_volume(date(2024, 4, 25), date(2024, 5, 28), 50),
        "GCM4": _flat_volume(date(2024, 4, 25), date(2024, 6, 26), 1000),
        "GCN4": _flat_volume(date(2024, 5, 27), date(2024, 7, 29), 50),
        "GCQ4": _flat_volume(date(2024, 6, 25), date(2024, 8, 28), 1000),
    }

    eligible = liquid_cycle(candidates, volume, roll_lead_days=5)

    assert tuple(contract.symbol for contract in eligible) == ("GCM4", "GCQ4")


def test_a_single_volume_spike_does_not_admit_a_serial() -> None:
    # GCK4 (serial) is dominated every day except one expiry-day print that tops the
    # liquid June contract.  A raw single-day argmax would admit it; smoothing over the
    # roll-lead window discounts the lone spike, so the serial stays out.
    liquid = _flat_volume(date(2024, 5, 1), date(2024, 5, 24), 1000)
    serial = _flat_volume(date(2024, 5, 1), date(2024, 5, 24), 50)
    serial.loc[pd.Timestamp("2024-05-15")] = 1100
    candidates = [
        DatedContract("GCK4", date(2024, 5, 24)),
        DatedContract("GCM4", date(2024, 6, 26)),
    ]
    volume = {"GCK4": serial, "GCM4": liquid}

    eligible = liquid_cycle(candidates, volume, roll_lead_days=5)

    assert tuple(contract.symbol for contract in eligible) == ("GCM4",)


def test_back_month_that_leads_only_late_in_life_stays_eligible() -> None:
    # GCQ4 trades thinly while GCM4 is front, then leads once GCM4 rolls off — it must
    # be admitted so the chain has a liquid contract to roll onto (epic user story 10).
    front = _flat_volume(date(2024, 5, 1), date(2024, 6, 26), 1000)
    back = pd.concat(
        [
            _flat_volume(date(2024, 5, 1), date(2024, 6, 26), 100),
            _flat_volume(date(2024, 6, 27), date(2024, 8, 28), 2000),
        ]
    )
    candidates = [
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    volume = {"GCM4": front, "GCQ4": back}

    eligible = liquid_cycle(candidates, volume, roll_lead_days=5)

    assert tuple(contract.symbol for contract in eligible) == ("GCM4", "GCQ4")


def test_a_candidate_with_no_volume_is_excluded() -> None:
    # A listed contract that never prints a bar (no volume) can never lead, so it is
    # excluded and the series still builds from the contracts that do trade.
    candidates = [
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCX4", date(2024, 7, 29)),
    ]
    volume = {
        "GCM4": _flat_volume(date(2024, 5, 1), date(2024, 6, 26), 1000),
        "GCX4": pd.Series(dtype="float64"),
    }

    eligible = liquid_cycle(candidates, volume, roll_lead_days=5)

    assert tuple(contract.symbol for contract in eligible) == ("GCM4",)


def test_equal_volume_sequential_contracts_all_stay_eligible() -> None:
    # Uniform volume must not spuriously drop a contract: each leads once the earlier
    # one expires, so the whole sequential chain stays eligible.
    candidates = [
        DatedContract("CLN6", date(2026, 6, 22)),
        DatedContract("CLQ6", date(2026, 7, 21)),
        DatedContract("CLU6", date(2026, 8, 20)),
    ]
    volume = {
        "CLN6": _flat_volume(date(2026, 5, 1), date(2026, 6, 22), 1000),
        "CLQ6": _flat_volume(date(2026, 6, 1), date(2026, 7, 21), 1000),
        "CLU6": _flat_volume(date(2026, 7, 1), date(2026, 8, 20), 1000),
    }

    eligible = liquid_cycle(candidates, volume, roll_lead_days=5)

    assert tuple(contract.symbol for contract in eligible) == ("CLN6", "CLQ6", "CLU6")


def test_no_candidates_yields_the_empty_liquid_cycle() -> None:
    assert liquid_cycle([], {}, roll_lead_days=5) == ()


def test_causal_liquid_cycle_admits_a_back_month_only_after_it_has_led() -> None:
    # GCQ4 leads only after GCM4 rolls off (late June).  As of mid-June it has not yet
    # led, so the causal rule excludes it; by end-August it has, so it is admitted.
    # Live selection never reads volume past as_of.
    candidates = [
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    volume = {
        "GCM4": _flat_volume(date(2024, 5, 1), date(2024, 6, 26), 1000),
        "GCQ4": pd.concat(
            [
                _flat_volume(date(2024, 5, 1), date(2024, 6, 26), 100),
                _flat_volume(date(2024, 6, 27), date(2024, 8, 28), 2000),
            ]
        ),
    }

    before = liquid_cycle_causal(candidates, volume, date(2024, 6, 15), roll_lead_days=5)
    after = liquid_cycle_causal(candidates, volume, date(2024, 8, 28), roll_lead_days=5)

    assert tuple(contract.symbol for contract in before) == ("GCM4",)
    assert tuple(contract.symbol for contract in after) == ("GCM4", "GCQ4")


def test_liquid_cycle_agreement_returns_the_shared_schedule_for_matching_feeds() -> None:
    candidates = [
        DatedContract("GCK4", date(2024, 5, 28)),
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    volume = {
        "GCK4": _flat_volume(date(2024, 4, 25), date(2024, 5, 28), 50),
        "GCM4": _flat_volume(date(2024, 4, 25), date(2024, 6, 26), 1000),
        "GCQ4": _flat_volume(date(2024, 6, 25), date(2024, 8, 28), 1000),
    }

    agreement = assert_liquid_cycle_agreement(
        "GC", candidates, volume, candidates, volume,
        date(2024, 5, 1), date(2024, 8, 1), roll_lead_days=5,
    )

    assert agreement.symbols == ("GCM4", "GCQ4")


def test_liquid_cycle_agreement_fails_closed_when_a_feed_makes_a_serial_lead() -> None:
    candidates = [
        DatedContract("GCK4", date(2024, 5, 28)),
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    research_volume = {
        "GCK4": _flat_volume(date(2024, 4, 25), date(2024, 5, 28), 50),
        "GCM4": _flat_volume(date(2024, 4, 25), date(2024, 6, 26), 1000),
        "GCQ4": _flat_volume(date(2024, 6, 25), date(2024, 8, 28), 1000),
    }
    live_volume = {
        **research_volume,
        "GCK4": _flat_volume(date(2024, 4, 25), date(2024, 5, 28), 5000),
    }

    with pytest.raises(RollAgreementError, match="GC"):
        assert_liquid_cycle_agreement(
            "GC", candidates, research_volume, candidates, live_volume,
            date(2024, 5, 1), date(2024, 8, 1), roll_lead_days=5,
        )


def test_liquid_cycle_agreement_tolerates_a_serial_listed_on_only_one_feed() -> None:
    # The live feed lists an extra serial (GCN4) the research feed does not; it never
    # leads, so it filters out and the post-filter schedules still agree.
    research_candidates = [
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    live_candidates = [
        DatedContract("GCM4", date(2024, 6, 26)),
        DatedContract("GCN4", date(2024, 7, 29)),
        DatedContract("GCQ4", date(2024, 8, 28)),
    ]
    research_volume = {
        "GCM4": _flat_volume(date(2024, 4, 25), date(2024, 6, 26), 1000),
        "GCQ4": _flat_volume(date(2024, 6, 25), date(2024, 8, 28), 1000),
    }
    live_volume = {
        **research_volume,
        "GCN4": _flat_volume(date(2024, 5, 27), date(2024, 7, 29), 50),
    }

    agreement = assert_liquid_cycle_agreement(
        "GC", research_candidates, research_volume, live_candidates, live_volume,
        date(2024, 5, 1), date(2024, 8, 1), roll_lead_days=5,
    )

    assert agreement.symbols == ("GCM4", "GCQ4")
