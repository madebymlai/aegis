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
    liquid_roll_schedule,
)
from aegis_data.roll import DatedContract, RollAgreementError, roll_schedule


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


def _palladium_early_crossover() -> tuple[list[DatedContract], dict[str, pd.Series]]:
    """A thin metal whose liquidity migrates early: PAM4 leads until the 2024-02-05 crossover, then
    PAU4 — weeks before PAM4's 2024-02-22 calendar roll (last trade 2024-02-29).  Shared by the
    Liquid-Cycle roll tests, which differ only in the window end and what they assert."""
    candidates = [DatedContract("PAM4", date(2024, 2, 29)), DatedContract("PAU4", date(2024, 5, 31))]
    crossover = pd.Timestamp("2024-02-05")
    front = pd.Series(
        [1000.0 if d < crossover else 1.0 for d in pd.bdate_range("2024-01-01", "2024-02-29")],
        index=pd.bdate_range("2024-01-01", "2024-02-29"), dtype="float64",
    )
    back = pd.Series(
        [10.0 if d < crossover else 5000.0 for d in pd.bdate_range("2024-01-01", "2024-04-01")],
        index=pd.bdate_range("2024-01-01", "2024-04-01"), dtype="float64",
    )
    return candidates, {"PAM4": front, "PAU4": back}


def test_liquid_roll_schedule_rolls_on_leadership_crossover_before_the_calendar_roll() -> None:
    # Thin metal: liquidity leaves the front (PAM4) in early Feb, weeks before its calendar
    # roll (last-trade 2024-02-29 -> 2024-02-22).  The seam must move EARLIER, onto the day
    # the back contract (PAU4) takes liquidity leadership, so no liquid day is stranded.
    candidates, volume = _palladium_early_crossover()

    schedule = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )
    calendar = roll_schedule(
        [c for c in candidates], date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )

    assert schedule.symbols == ("PAM4", "PAU4")
    assert calendar.roll_dates[0] == date(2024, 2, 22)  # the unchanged calendar roll
    assert schedule.roll_dates[0] < date(2024, 2, 22)  # moved earlier, onto the crossover
    assert date(2024, 2, 5) <= schedule.roll_dates[0] <= date(2024, 2, 13)


def test_liquid_roll_schedule_keeps_the_calendar_roll_when_liquidity_tracks_expiry() -> None:
    # Liquid root: the front leads right up to its last trade, the back leads only after.
    # The crossover lands after the calendar roll, so the cap is a no-op — no regression for
    # CL/GC-style roots whose liquidity migrates near expiry.
    candidates = [
        DatedContract("CLG4", date(2024, 2, 29)),
        DatedContract("CLJ4", date(2024, 5, 31)),
    ]
    front = pd.Series(
        [1000.0] * len(pd.bdate_range("2024-01-01", "2024-02-29")),
        index=pd.bdate_range("2024-01-01", "2024-02-29"), dtype="float64",
    )
    back = pd.Series(
        [100.0 if d <= pd.Timestamp("2024-02-29") else 2000.0
         for d in pd.bdate_range("2024-01-01", "2024-04-01")],
        index=pd.bdate_range("2024-01-01", "2024-04-01"), dtype="float64",
    )
    volume = {"CLG4": front, "CLJ4": back}

    schedule = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )

    assert schedule.roll_dates[0] == date(2024, 2, 22)  # unchanged calendar roll


def test_liquid_roll_schedule_recovers_a_liquidity_leader_truncated_by_the_window_end() -> None:
    # Thin metal again, but the window END (2024-02-16) lands BETWEEN the early crossover
    # (2024-02-05) and the front's calendar roll (2024-02-22) — the live case, where end=now is
    # mid-roll-window.  By the calendar PAM4 is still front, so roll_schedule's window drops PAU4;
    # but liquidity has already migrated to PAU4, so the chain must EXTEND onto it (rolling at the
    # crossover) rather than strand the series on the thinning PAM4.
    candidates, volume = _palladium_early_crossover()

    windowed = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 2, 16), roll_lead_days=5
    )
    full = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )

    assert windowed.symbols == ("PAM4", "PAU4")          # PAU4 recovered, not truncated by the edge
    assert windowed.roll_dates == (date(2024, 2, 5),)    # rolled at the crossover, not the 02-22 calendar
    assert windowed.roll_dates == full.roll_dates        # the window edge does not move the roll date


def test_liquid_roll_schedule_does_not_roll_onto_an_eligible_leg_before_its_crossover() -> None:
    # The correctness gate: the late-edge extension triggers on a CONFIRMED leadership crossover
    # (smoothed, on/before end), not on eligibility.  A leg that is eligible — it *ever* leads, so it
    # is in the Liquid Cycle — but whose crossover has not happened by end must NOT be pulled in;
    # rolling on eligibility alone would trade the back month before liquidity actually migrated.
    candidates, volume = _palladium_early_crossover()

    # PAU4 is eligible (it will take the lead) ...
    assert tuple(c.symbol for c in liquid_cycle(candidates, volume, roll_lead_days=5)) == ("PAM4", "PAU4")
    # ... but with end (2024-02-02) before its crossover (2024-02-05) the chain stays on PAM4: no early roll.
    schedule = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 2, 2), roll_lead_days=5
    )
    assert schedule.symbols == ("PAM4",)
    assert schedule.roll_dates == ()


def test_liquid_roll_schedule_roll_dates_are_causal() -> None:
    # The roll only ever depends on trailing volume, so truncating every series to the
    # resulting roll date reproduces the same roll — the guarantee that the live (causal)
    # and research (acausal) roll dates coincide, preserving backtest/live parity.
    candidates, volume = _palladium_early_crossover()

    acausal = liquid_roll_schedule(
        candidates, volume, date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )
    roll = pd.Timestamp(acausal.roll_dates[0])
    causal_volume = {symbol: series[series.index <= roll] for symbol, series in volume.items()}
    causal = liquid_roll_schedule(
        candidates, causal_volume, date(2024, 1, 1), date(2024, 4, 1), roll_lead_days=5
    )

    assert causal.roll_dates == acausal.roll_dates


def test_causal_front_picker_agrees_with_the_roll_schedule_front() -> None:
    # Green here is the gate that lets the continuous model retire the second
    # front-picker: the front leg used for execution and the schedule leg used
    # for materialisation are the same at representative as-ofs, including the
    # early liquidity migration that guards bd aegis-rd-6qp.
    candidates, volume = _palladium_early_crossover()
    _assert_front_picker_agrees(candidates, volume, date(2024, 1, 1), date(2024, 2, 2))
    _assert_front_picker_agrees(candidates, volume, date(2024, 1, 1), date(2024, 2, 16))
    _assert_front_picker_agrees(candidates, volume, date(2024, 1, 1), date(2024, 4, 1))

    liquid_root = [
        DatedContract("CLG4", date(2024, 2, 29)),
        DatedContract("CLJ4", date(2024, 5, 31)),
    ]
    liquid_volume = {
        "CLG4": _flat_volume(date(2024, 1, 1), date(2024, 2, 29), 1000),
        "CLJ4": pd.Series(
            [
                100.0 if d <= pd.Timestamp("2024-02-29") else 2000.0
                for d in pd.bdate_range("2024-01-01", "2024-04-01")
            ],
            index=pd.bdate_range("2024-01-01", "2024-04-01"),
            dtype="float64",
        ),
    }
    _assert_front_picker_agrees(liquid_root, liquid_volume, date(2024, 1, 1), date(2024, 2, 15))
    _assert_front_picker_agrees(liquid_root, liquid_volume, date(2024, 1, 1), date(2024, 4, 1))


def _assert_front_picker_agrees(
    candidates: list[DatedContract],
    volume: dict[str, pd.Series],
    start: date,
    as_of: date,
) -> None:
    causal = liquid_cycle_causal(candidates, volume, as_of, roll_lead_days=5)
    schedule = liquid_roll_schedule(candidates, volume, start, as_of, roll_lead_days=5)

    assert causal
    assert schedule.symbols
    assert causal[-1].symbol == schedule.symbols[-1]


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
