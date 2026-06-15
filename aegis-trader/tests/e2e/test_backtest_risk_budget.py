"""Risk-budget e2e: 5-year covariance vol-target budget and attribution."""

from __future__ import annotations

import numpy as np
import pytest

from aegis_trader.domain.allocator import covariance_book_vol, risk_contribution_shares
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import (
    BookConfig,
    ConvexityBudgetCandidate,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.types import SleeveName

_TREND = SleeveName("trend")
_TAIL = SleeveName("tail")
_EXPANSION = SleeveName("expansion")


def test_five_year_covariance_risk_budget_hits_vol_target_and_attribution_reconciles():
    """Tracer for the commingled backtest invariant without external data/wheels.

    Five years of synthetic daily sleeve returns produce a realized covariance
    input.  The rebalancer must use the allocator seam (not static capital
    budgets): the higher-vol tail receives half the capital multiplier of the
    lower-vol trend in the zero-correlation limit, the book hits the configured
    annualized vol target, and attribution sums back to the realized NAV change.
    """
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = {
        _TREND: {
            _TREND: float(np.var(trend_returns, ddof=1) * 252.0),
            _TAIL: float(np.cov(trend_returns, tail_returns, ddof=1)[0, 1] * 252.0),
        },
        _TAIL: {
            _TREND: float(np.cov(trend_returns, tail_returns, ddof=1)[0, 1] * 252.0),
            _TAIL: float(np.var(tail_returns, ddof=1) * 252.0),
        },
    }

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
            realized_weights=weights,
            sleeve_targets={_TREND: {"TREND": 1.0}, _TAIL: {"TAIL": 1.0}},
            closes={"TREND": 100.0, "TAIL": 100.0},
        ),
        AttributionPeriod(
            nav=nav,
            realized_weights=weights,
            sleeve_targets={_TREND: {"TREND": 1.0}, _TAIL: {"TAIL": 1.0}},
            closes={"TREND": 101.0, "TAIL": 98.0},
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


def test_five_year_tail_convexity_budget_bounds_target_risk_and_zeros_expansion():
    """A convexity-unit Target budget keeps the tail from dominating risk."""
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
    covariance = {
        left: {
            right: float(np.cov(left_returns, right_returns, ddof=1)[0, 1] * 252.0)
            for right, right_returns in returns.items()
        }
        for left, left_returns in returns.items()
    }

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
            coverage_target_units=1.0,
            unit_payoff_fraction_at_20_down=0.01,
            candidates=(
                ConvexityBudgetCandidate(
                    sleeve=_TAIL,
                    expected_annual_payoff=0.24,
                    annual_carry=0.08,
                    crisis_reliability=0.75,
                    convexity_units_per_risk_share=20.0,
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


def _one_row_target(figi_to_weight: dict[str, float]):
    import pandas as pd

    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df
