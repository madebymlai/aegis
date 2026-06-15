"""Risk-budget tracer e2e: 5-year diagonal vol-target budget and attribution."""

from __future__ import annotations

import numpy as np
import pytest

from aegis_trader.domain.allocator import diagonal_book_vol
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import BookConfig, RiskGroup, SleeveConfig
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.types import SleeveName

_TREND = SleeveName("trend")
_TAIL = SleeveName("tail")


def test_five_year_diagonal_risk_budget_hits_vol_target_and_attribution_reconciles():
    """Tracer for the commingled backtest invariant without external data/wheels.

    Five years of synthetic daily sleeve returns produce realized vol inputs.  The
    rebalancer must use the allocator seam (not static capital budgets): the
    higher-vol tail receives half the capital multiplier of the lower-vol trend,
    the diagonal book hits the configured annualized vol target, and the
    attribution decomposition sums back to the realized-weight NAV change.
    """
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    trend_vol = float(np.std(trend_returns, ddof=1) * np.sqrt(252.0))
    tail_vol = float(np.std(tail_returns, ddof=1) * np.sqrt(252.0))

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
        realized_vols={_TREND: trend_vol, _TAIL: tail_vol},
    )
    weights = {delta.figi.value: delta.delta for delta in deltas}

    assert weights["TAIL"] == pytest.approx(weights["TREND"] / 2.0, rel=0.02)
    assert diagonal_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        {_TREND: trend_vol, _TAIL: tail_vol},
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


def _one_row_target(figi_to_weight: dict[str, float]):
    import pandas as pd

    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df
