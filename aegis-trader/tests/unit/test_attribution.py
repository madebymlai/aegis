"""Unit tests for per-sleeve P&L attribution — pure domain, zero Nautilus.

Attribution decomposes the *realized* book return across sleeves so it
reconciles to book P&L: per period the book's gain is

    Σ_i realized_w_{i,t-1} × return_{i,t} × NAV_{t-1}

(the realized-weight return identity), and each instrument's realized weight is
split across sleeves by their *budget-scaled target* share.  Because the shares
sum to 1 per instrument, the per-sleeve P&Ls sum back to the book P&L.
"""

from __future__ import annotations

import pytest

from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.types import Figi, SleeveName

_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")


def test_single_sleeve_full_budget_is_realized_weight_times_return():
    """One sleeve at budget 1.0: P&L = realized_weight × return × NAV per period."""
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.5},
                          sleeve_targets={_TREND: {Figi("A"): 0.5}}, closes={Figi("A"): 100.0}),
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.5},
                          sleeve_targets={_TREND: {Figi("A"): 0.5}}, closes={Figi("A"): 110.0}),
    ]

    result = compute_sleeve_attribution(periods, budgets={_TREND: 1.0})

    # realized 0.5 × (110/100 - 1 = 0.10) × NAV 100_000 = 5_000
    assert result[_TREND] == pytest.approx(5_000.0)


def _book_pnl(periods) -> float:
    """The realized-weight book P&L the sleeves must reconcile to."""
    total = 0.0
    for prev, curr in zip(periods, periods[1:]):
        for figi, w in prev.realized_weights.items():
            total += w * (curr.closes[figi] / prev.closes[figi] - 1.0) * prev.nav
    return total


def test_sleeve_attributions_sum_to_book_pnl():
    """Two sleeves whose budget-scaled targets net to the realized book: the
    per-sleeve P&Ls sum to the book's realized-weight P&L."""
    budgets = {_TREND: 0.6, _CARRY: 0.4}
    trend_t = {Figi("A"): 1.0, Figi("B"): 0.5}
    carry_t = {Figi("A"): -0.5, Figi("C"): 1.0}
    # realized = Σ budget × target: A=0.6-0.2=0.4, B=0.3, C=0.4
    realized = {Figi("A"): 0.4, Figi("B"): 0.3, Figi("C"): 0.4}
    closes = [
        {Figi("A"): 100.0, Figi("B"): 50.0, Figi("C"): 200.0},
        {Figi("A"): 105.0, Figi("B"): 52.0, Figi("C"): 210.0},
        {Figi("A"): 110.0, Figi("B"): 48.0, Figi("C"): 215.0},
    ]
    navs = [100_000.0, 102_000.0, 101_000.0]
    periods = [
        AttributionPeriod(nav=navs[i], realized_weights=realized,
                          sleeve_targets={_TREND: trend_t, _CARRY: carry_t}, closes=closes[i])
        for i in range(3)
    ]

    result = compute_sleeve_attribution(periods, budgets=budgets)

    assert result[_TREND] + result[_CARRY] == pytest.approx(_book_pnl(periods), rel=1e-12)


def test_shared_figi_split_by_budget_scaled_target_share():
    """Two sleeves on the same FIGI split its P&L by budget×target proportion."""
    budgets = {_TREND: 0.6, _CARRY: 0.4}
    # intended: trend 0.6×1.0=0.6, carry 0.4×0.5=0.2 -> total 0.8 (= realized)
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.8},
                          sleeve_targets={_TREND: {Figi("A"): 1.0}, _CARRY: {Figi("A"): 0.5}},
                          closes={Figi("A"): 100.0}),
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.8},
                          sleeve_targets={_TREND: {Figi("A"): 1.0}, _CARRY: {Figi("A"): 0.5}},
                          closes={Figi("A"): 110.0}),
    ]

    result = compute_sleeve_attribution(periods, budgets=budgets)

    # book_contrib = 0.8 × 0.10 × 100_000 = 8_000; shares 0.6/0.8 and 0.2/0.8
    assert result[_TREND] == pytest.approx(6_000.0)
    assert result[_CARRY] == pytest.approx(2_000.0)


def test_untargeted_realized_position_splits_by_budget_fraction():
    """A realized position no sleeve targets is split by budget fraction so the
    book P&L still reconciles (no P&L silently dropped)."""
    budgets = {_TREND: 0.75, _CARRY: 0.25}
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.4},
                          sleeve_targets={_TREND: {}, _CARRY: {}}, closes={Figi("A"): 100.0}),
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.4},
                          sleeve_targets={_TREND: {}, _CARRY: {}}, closes={Figi("A"): 110.0}),
    ]

    result = compute_sleeve_attribution(periods, budgets=budgets)

    # book_contrib = 0.4 × 0.10 × 100_000 = 4_000; split 0.75/0.25
    assert result[_TREND] == pytest.approx(3_000.0)
    assert result[_CARRY] == pytest.approx(1_000.0)
    assert result[_TREND] + result[_CARRY] == pytest.approx(_book_pnl(periods))


def test_short_realized_weight_reverses_sign():
    """A negative realized weight (net short) flips the P&L sign on a rising price."""
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): -0.5},
                          sleeve_targets={_TREND: {Figi("A"): -0.5}}, closes={Figi("A"): 100.0}),
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): -0.5},
                          sleeve_targets={_TREND: {Figi("A"): -0.5}}, closes={Figi("A"): 110.0}),
    ]
    assert compute_sleeve_attribution(periods, budgets={_TREND: 1.0})[_TREND] < 0


def test_figi_missing_a_close_contributes_nothing():
    """A FIGI without a usable close pair is skipped (no fabricated return)."""
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.5, Figi("GAP"): 0.5},
                          sleeve_targets={_TREND: {Figi("A"): 0.5, Figi("GAP"): 0.5}},
                          closes={Figi("A"): 100.0}),  # GAP has no close
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.5, Figi("GAP"): 0.5},
                          sleeve_targets={_TREND: {Figi("A"): 0.5, Figi("GAP"): 0.5}},
                          closes={Figi("A"): 110.0}),
    ]
    result = compute_sleeve_attribution(periods, budgets={_TREND: 1.0})
    assert result[_TREND] == pytest.approx(0.5 * 0.10 * 100_000.0)  # only A


def test_single_period_has_no_returns():
    periods = [
        AttributionPeriod(nav=100_000.0, realized_weights={Figi("A"): 0.5},
                          sleeve_targets={_TREND: {Figi("A"): 0.5}}, closes={Figi("A"): 100.0}),
    ]
    assert compute_sleeve_attribution(periods, budgets={_TREND: 1.0})[_TREND] == pytest.approx(0.0)


def test_no_budgets_returns_empty():
    assert compute_sleeve_attribution([], budgets={}) == {}
