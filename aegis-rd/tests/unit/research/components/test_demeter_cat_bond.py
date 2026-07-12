from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle
from research.aegis_research.external_data.catb_portfolio import CatbPortfolioMetrics
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

_ROOT = Path(__file__).resolve().parents[4]


def _load(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _close(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {InstrumentId.from_str("CATB.LSEETF"): np.linspace(10.0, 10.5, len(index))},
        index=index,
    )


def test_cat_bond_calendar_marks_first_observation_of_each_month() -> None:
    component = _load(
        "research/components/indicators/demeter/cat_bond_calendar.py",
        "demeter_cat_bond_calendar_test",
    )
    close = _close(pd.to_datetime(["2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03"]))

    result = component.run(
        MarketDataBundle(arrays={"Close": close}),
        n_candidates=1,
        rebalance_interval_months=[1],
    )["rebalance_due"]

    np.testing.assert_array_equal(result[:, 0], [1.0, 0.0, 1.0, 0.0])


def test_catb_portfolio_cache_is_unavailable_before_recorded_retrieval() -> None:
    component = _load(
        "research/components/indicators/demeter/cat_bond_portfolio_carry.py",
        "demeter_cat_bond_portfolio_carry_test",
    )
    index = pd.to_datetime(["2026-07-12", "2026-07-13", "2026-08-28"])
    component.current_and_cached_metrics = lambda *args, **kwargs: [
        CatbPortfolioMetrics(
            available_at=datetime(2026, 7, 12, tzinfo=UTC),
            insurance_spread=14.0,
            expected_loss=5.0,
            net_carry=11.47,
            risk_multiple=2.8,
            coverage=0.103,
        )
    ]

    result = component.run(
        MarketDataBundle(arrays={"Close": _close(index)}),
        n_candidates=1,
        cache_dir=["unused"],
        history_dir=["unused"],
        enrichment=["unused"],
        max_age_days=[45],
        collateral_yield=[3.75],
        fund_fee=[1.28],
    )

    assert np.isnan(result["cat_bond_net_carry"][0, 0])
    assert result["cat_bond_data_fresh"][:, 0].tolist() == [0.0, 1.0, 0.0]
    assert result["cat_bond_data_coverage"][1, 0] == pytest.approx(0.103)


def test_cat_bond_strategy_emits_targets_only_on_rebalance_rows() -> None:
    component = _load(
        "research/components/strategies/demeter/cat_bond_income.py",
        "demeter_cat_bond_income_test",
    )
    index = pd.date_range("2026-01-29", periods=4, freq="D")
    close = _close(index)
    inputs = ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={
            "rebalance_due": np.array([[1.0], [0.0], [0.0], [1.0]]),
            "cat_bond_net_carry": np.full((4, 1), 5.0),
            "cat_bond_risk_multiple": np.full((4, 1), 4.0),
            "cat_bond_data_coverage": np.ones((4, 1)),
            "cat_bond_data_fresh": np.ones((4, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_weight=[0.05],
        max_weight=[0.30],
        low_multiple=[2.0],
        high_multiple=[4.0],
        min_coverage=[0.8],
    )

    np.testing.assert_allclose(result[[0, 3], 0], [0.30, 0.30])
    assert np.isnan(result[[1, 2], 0]).all()


def test_cat_bond_strategy_scales_between_floor_and_cap_with_risk_multiple() -> None:
    component = _load(
        "research/components/strategies/demeter/cat_bond_income.py",
        "demeter_cat_bond_income_risk_budget_test",
    )
    index = pd.date_range("2026-01-29", periods=2, freq="D")
    close = _close(index)
    inputs = ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={
            "rebalance_due": np.array([[1.0], [0.0]]),
            "cat_bond_net_carry": np.full((2, 1), 5.0),
            "cat_bond_risk_multiple": np.full((2, 1), 3.0),
            "cat_bond_data_coverage": np.ones((2, 1)),
            "cat_bond_data_fresh": np.ones((2, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_weight=[0.10],
        max_weight=[0.30],
        low_multiple=[2.0],
        high_multiple=[4.0],
        min_coverage=[0.8],
    )

    assert result[0, 0] == 0.20


def test_cat_bond_strategy_keeps_fixed_floor_when_lookthrough_coverage_is_low() -> None:
    component = _load(
        "research/components/strategies/demeter/cat_bond_income.py",
        "demeter_cat_bond_income_low_coverage_test",
    )
    index = pd.date_range("2026-07-09", periods=1, freq="D")
    close = _close(index)
    inputs = ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={
            "rebalance_due": np.ones((1, 1)),
            "cat_bond_net_carry": np.full((1, 1), 12.0),
            "cat_bond_risk_multiple": np.full((1, 1), 3.5),
            "cat_bond_data_coverage": np.full((1, 1), 0.5),
            "cat_bond_data_fresh": np.ones((1, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_weight=[0.05],
        max_weight=[0.25],
        low_multiple=[2.0],
        high_multiple=[4.0],
        min_coverage=[0.8],
    )

    assert result[0, 0] == 0.05
