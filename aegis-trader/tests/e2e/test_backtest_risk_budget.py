"""Risk-budget e2e: 5-year covariance vol-target budget and attribution."""

from __future__ import annotations

import numpy as np
import pytest

from aegis_trader.domain.allocator import covariance_book_vol, risk_contribution_shares
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import (
    BookConfig,
    ConvexityBudgetCandidate,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.rebalancer import rebalance, rebalance_plan
from aegis_trader.domain.types import Figi, SleeveName

_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")
_TAIL = SleeveName("tail")
_EXPANSION = SleeveName("expansion")


def test_five_year_covariance_risk_budget_hits_vol_target_and_attribution_reconciles():
    """Tracer for the commingled backtest invariant without external data/wheels.

    Five years of synthetic daily sleeve returns produce a realized covariance
    input.  The rebalancer must use the allocator seam (not static capital
    budgets): the higher-vol tail receives half the capital multiplier of the
    lower-vol trend in the zero-correlation limit, the book hits the configured
    annualized vol target when leverage is permitted (``max_book_gross`` headroom,
    so the down-only clamp does not bind), and attribution sums back to the
    realized NAV change.
    """
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = _annualized_covariance(
        {
            _TREND: trend_returns,
            _TAIL: tail_returns,
        }
    )

    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.5,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.5,
                group=RiskGroup.TARGET,
            ),
        ),
        book_vol_target=0.09,
        max_book_gross=2.0,  # permit leverage so the solve hits the target (clamp tested separately)
    )

    target = _one_row_target
    deltas = rebalance(
        {
            _TREND: target({"TREND": 1.0}),
            _TAIL: target({"TAIL": 1.0}),
        },
        book,
        realized_covariance=covariance,
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    assert weights["TAIL"] == pytest.approx(weights["TREND"] / 2.0, rel=0.02)
    assert covariance_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        covariance,
    ) == pytest.approx(book.book_vol_target)

    nav = 1_000_000.0
    periods = [
        AttributionPeriod(
            nav=nav,
            realized_weights={Figi(k): v for k, v in weights.items()},
            sleeve_targets={_TREND: {Figi("TREND"): 1.0}, _TAIL: {Figi("TAIL"): 1.0}},
            closes={Figi("TREND"): 100.0, Figi("TAIL"): 100.0},
        ),
        AttributionPeriod(
            nav=nav,
            realized_weights={Figi(k): v for k, v in weights.items()},
            sleeve_targets={_TREND: {Figi("TREND"): 1.0}, _TAIL: {Figi("TAIL"): 1.0}},
            closes={Figi("TREND"): 101.0, Figi("TAIL"): 98.0},
        ),
    ]
    attribution = compute_sleeve_attribution(
        periods,
        budgets={_TREND: 0.5, _TAIL: 0.5},
    )
    book_pnl = (
        weights["TREND"] * 0.01
        + weights["TAIL"] * -0.02
    ) * nav

    assert sum(attribution.values()) == pytest.approx(book_pnl)


def test_down_only_clamp_runs_unlevered_book_as_a_vol_ceiling():
    """An unlevered book (gross_cap = max_book_gross = 1.0) whose vol-target solve
    over-levers no longer fails closed: the down-only clamp holds gross at the cap
    and realized vol sits below the target as a ceiling (ADR-0004 amendment)."""
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = _annualized_covariance({_TREND: trend_returns, _TAIL: tail_returns})

    book = BookConfig(
        sleeves=(
            SleeveConfig(name=_TREND, wheel_filename="trend.whl", risk_share=0.5, group=RiskGroup.FLOOR),
            SleeveConfig(name=_TAIL, wheel_filename="tail.whl", risk_share=0.5, group=RiskGroup.TARGET),
        ),
        book_vol_target=0.09,
        max_book_gross=1.0,
        gross_cap=1.0,
    )

    # The solve wants ~1.35x gross to peg 9%; previously this raised
    # "Gross exposure ... exceeds cap".  The down-only clamp now lets it run.
    deltas = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0}), _TAIL: _one_row_target({"TAIL": 1.0})},
        book,
        realized_covariance=covariance,
    )
    weights = {d.figi.value: d.delta for d in deltas}
    gross = sum(abs(v) for v in weights.values())

    # Clamp bound at the cap -> proves the solve had over-levered past it.
    assert gross == pytest.approx(book.max_book_gross)
    # Realized book vol is a ceiling, below target (not pegged up via leverage).
    assert covariance_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]}, covariance
    ) < book.book_vol_target


def test_five_year_tail_convexity_budget_bounds_target_risk_and_zeros_expansion():
    """A convexity-premium Target budget keeps the tail from dominating risk."""
    days = 252 * 5
    x = np.linspace(0.0, 50.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.70 / np.sqrt(252.0) * np.cos(x)
    expansion_returns = 0.15 / np.sqrt(252.0) * np.sin(x + 0.4)
    returns = {
        _TREND: trend_returns,
        _TAIL: tail_returns,
        _EXPANSION: expansion_returns,
    }
    covariance = _annualized_covariance(returns)

    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.60,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.90,  # ignored: Target risk is set by the convexity budget
                group=RiskGroup.TARGET,
            ),
            SleeveConfig(
                name=_EXPANSION,
                wheel_filename="expansion.whl",
                risk_share=0.40,  # ignored until Expansion earns an explicit budget
                group=RiskGroup.EXPANSION,
            ),
        ),
        book_vol_target=0.09,
        tail_convexity_budget=TailConvexityBudget(
            attachment=-0.20,
            coverage_target=0.01,
            annual_carry_budget=0.0075,
            candidates=(
                ConvexityBudgetCandidate(
                    sleeve=_TAIL,
                    payoff_at_attachment=0.20,
                    annual_carry=0.08,
                    crisis_reliability=0.75,
                    capacity_risk_share=0.05,
                ),
            ),
        ),
    )

    deltas = rebalance(
        {
            _TREND: _one_row_target({"TREND": 1.0}),
            _TAIL: _one_row_target({"TAIL": 1.0}),
            _EXPANSION: _one_row_target({"EXPANSION": 1.0}),
        },
        book,
        realized_covariance=covariance,
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    assert "EXPANSION" not in weights
    realized_risk = risk_contribution_shares(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        {_TREND: covariance[_TREND], _TAIL: covariance[_TAIL]},
    )
    assert realized_risk[_TAIL] < 0.02
    assert realized_risk[_TAIL] < realized_risk[_TREND]
    assert weights["TAIL"] < weights["TREND"] * 0.02


def _annualized_covariance(
    returns: dict[SleeveName, np.ndarray],
) -> dict[SleeveName, dict[SleeveName, float]]:
    return {
        left: {
            right: float(np.cov(left_returns, right_returns, ddof=1)[0, 1] * 252.0)
            for right, right_returns in returns.items()
        }
        for left, left_returns in returns.items()
    }


def _one_row_target(figi_to_weight: dict[str, float]):
    import pandas as pd

    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df


def test_sleeve_bands_cut_turnover_while_vol_target_stays_close():
    """Synthetic two-period revalidation of the sleeve-band allocator seam."""
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.5,
                group=RiskGroup.FLOOR,
                weight_band_down=0.01,
                weight_band_up=0.01,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.5,
                group=RiskGroup.TARGET,
                weight_band_down=0.01,
                weight_band_up=0.01,
            ),
        ),
        book_vol_target=0.09,
        sleeve_reversion_fraction=0.5,
    )
    targets = {_TREND: _one_row_target({"TREND": 1.0}), _TAIL: _one_row_target({"TAIL": 1.0})}
    first_covariance = {
        _TREND: {_TREND: 0.10**2, _TAIL: 0.0},
        _TAIL: {_TREND: 0.0, _TAIL: 0.10**2},
    }
    second_covariance = {
        _TREND: {_TREND: 0.10**2, _TAIL: 0.0},
        _TAIL: {_TREND: 0.0, _TAIL: 0.102**2},
    }

    first = rebalance_plan(targets, book, realized_covariance=first_covariance)
    full_second = rebalance_plan(targets, book, realized_covariance=second_covariance)
    banded_second = rebalance_plan(
        targets,
        book,
        realized_covariance=second_covariance,
        previous_sleeve_weights=dict(first.applied_sleeve_weights),
    )

    full_turnover = sum(
        abs(full_second.applied_sleeve_weights[name] - first.applied_sleeve_weights[name])
        for name in first.applied_sleeve_weights
    )
    banded_turnover = sum(
        abs(banded_second.applied_sleeve_weights[name] - first.applied_sleeve_weights[name])
        for name in first.applied_sleeve_weights
    )

    assert banded_turnover < full_turnover
    assert banded_turnover == pytest.approx(full_turnover / 2.0)
    assert covariance_book_vol(
        dict(banded_second.applied_sleeve_weights),
        second_covariance,
    ) == pytest.approx(book.book_vol_target, abs=0.001)


def test_all_concave_floor_allocates_by_conviction_tilt_with_no_skew_enforcement():
    """Net-convexity is by construction (ADR-0004 amendment), not a live solve.

    Both Floor poles can be transiently concave with no convex donor — the case
    that used to raise "skew constraint cannot be satisfied" (the bu4.7 blocker).
    With the live skew solve removed, the book simply allocates by its risk-budget
    conviction tilt (trend the larger pole) and completes; there is no skew
    machinery left to go infeasible.
    """
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.6,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_CARRY,
                wheel_filename="carry.whl",
                risk_share=0.4,
                group=RiskGroup.FLOOR,
            ),
        ),
        book_vol_target=0.09,
        max_book_gross=2.0,  # isolate from the down-only clamp; this is about skew
    )

    # The allocator no longer takes any skew input; an all-concave Floor is just
    # ordinary data it allocates over.
    deltas = rebalance(
        {
            _TREND: _one_row_target({"TREND": 1.0}),
            _CARRY: _one_row_target({"CARRY": 1.0}),
        },
        book,
        realized_covariance={
            _TREND: {_TREND: 0.10**2, _CARRY: 0.0},
            _CARRY: {_TREND: 0.0, _CARRY: 0.10**2},
        },
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    # Completed (no infeasibility) and kept the conviction tilt: trend > carry.
    assert weights["TREND"] > weights["CARRY"]


def test_backtest_drawdown_delever_engages_in_worst_window_and_returns_are_measured():
    """Backtest seam: NAV drawdown from the engine drives a book-level de-lever.

    A five-year synthetic path opens with an early crash, stays in the trough,
    then heals.  The strategy computes drawdown from its recorded NAV path and
    passes it to the allocator; the observable effect is a sell order while the
    bundle still asks for a constant long target.
    """
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=1.0,
                group=RiskGroup.FLOOR,
            ),
        ),
        book_vol_target=0.09,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05,
            end_drawdown=0.25,
            floor_multiplier=0.50,
        ),
    )

    # No drawdown: full allocation.
    deltas = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.0,
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    # Deep drawdown: scaled allocation.
    stressed = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.25,
    )
    stressed_weights = {delta.figi.value: delta.delta for delta in stressed}
    assert stressed_weights["TREND"] == pytest.approx(weights["TREND"] * 0.50)

    # Recovery returns to full.
    recovered = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.04,
    )
    recovered_weights = {delta.figi.value: delta.delta for delta in recovered}
    assert recovered_weights["TREND"] == pytest.approx(weights["TREND"])
