"""Justification gate (aegis-rd-kqg.10, original handoff Q7).

A reproducible carry-off vs carry-on comparison on a representative market-neutral
long/short grid. It answers — before the rest of the financing-carry epic is built —
whether short financing carry materially reorders the representative Candidates
(best/median/worst). The demo charges carry through the *settled* mechanism that will
ship: a per-bar ``cash_dividends`` array masked to the short legs, passed to
``Portfolio.from_optimizer`` (the same factory the simulator uses). See ADR-0007 and
``docs/adr/0008-*`` (financing carry).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.optimization.financing_carry_demo import (
    PERIODS_PER_YEAR,
    CarryRankingComparison,
    compare_carry_ranking_bias,
    short_masked_cash_dividends,
)


def test_short_carry_reorders_best_and_worst_candidate_selection() -> None:
    # On a market-neutral grid whose candidates differ only in short notional, a tiny
    # price edge makes the heaviest-short book the pre-carry winner. Short borrow carry
    # — proportional to short size — falls hardest on that same book, so at the shipping
    # default rate the best and worst Candidates swap. If they did NOT swap, that would be
    # the signal to stop before building the rest of the epic.
    comparison = compare_carry_ranking_bias()

    assert isinstance(comparison, CarryRankingComparison)
    assert comparison.reordered is True
    # The heaviest-short book wins pre-carry and loses post-carry: a full best<->worst flip.
    assert comparison.carry_off_best != comparison.carry_on_best
    assert comparison.carry_off_best == comparison.carry_on_worst
    assert comparison.carry_on_best == comparison.carry_off_worst


def test_comparison_records_a_justification_note_for_the_build_decision() -> None:
    # Acceptance criterion: the result must be *recorded* so the build decision is justified
    # either way. The comparison serializes to a structured, schema-tagged note carrying the
    # carry-off vs carry-on selection, the rate it was charged at, and the reorder verdict.
    comparison = compare_carry_ranking_bias()

    note = comparison.as_note()

    assert note["verdict"] == "reordered"
    assert note["short_borrow_rate"] == 0.005
    assert note["mechanism"] == "cash_dividends_short_borrow"
    assert note["carry_off"] == {
        "best": comparison.carry_off_best,
        "median": comparison.carry_off_median,
        "worst": comparison.carry_off_worst,
    }
    assert note["carry_on"] == {
        "best": comparison.carry_on_best,
        "median": comparison.carry_on_median,
        "worst": comparison.carry_on_worst,
    }


def test_carry_is_charged_only_on_short_legs_via_masked_cash_dividends() -> None:
    # "Matches what ships": carry is a positive per-share cash_dividends masked to the short
    # legs only (a positive per-share dividend is a COST on a short, a CREDIT on a long, so
    # long legs must be zeroed). The short charge is rate_per_bar * close — the drifted-
    # notional base falls out of cash_dividends * live position downstream.
    index = pd.date_range("2024-01-01", periods=3)
    close = pd.DataFrame(
        {"LONG": [100.0, 110.0, 120.0], "SHORT": [50.0, 55.0, 60.0]}, index=index
    )
    allocations = pd.DataFrame(
        {"LONG": [0.5, np.nan, np.nan], "SHORT": [-0.5, np.nan, np.nan]}, index=index
    )

    cash_dividends = short_masked_cash_dividends(
        close, allocations, short_borrow_rate=0.005
    )

    rate_per_bar = 0.005 / PERIODS_PER_YEAR
    assert (cash_dividends["LONG"] == 0.0).all()
    assert cash_dividends["SHORT"].tolist() == [
        rate_per_bar * price for price in close["SHORT"].tolist()
    ]
