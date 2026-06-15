"""Risk-budget e2e: 5-year covariance vol-target budget and attribution."""

from __future__ import annotations

import numpy as np
import pytest

from aegis_trader.domain.allocator import covariance_book_vol
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import BookConfig, RiskGroup, SleeveConfig
from aegis_trader.domain.rebalancer import rebalance, rebalance_plan
from aegis_trader.domain.types import SleeveName

_TREND = SleeveName("trend")
_TAIL = SleeveName("tail")


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


def _one_row_target(figi_to_weight: dict[str, float]):
    import pandas as pd

    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df
