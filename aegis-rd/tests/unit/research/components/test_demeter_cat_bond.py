from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle
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
            "cat_bond_richness": np.full((4, 1), 1.2),
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
        low_richness=[0.8],
        high_richness=[1.2],
    )

    np.testing.assert_allclose(result[[0, 3], 0], [0.30, 0.30])
    assert np.isnan(result[[1, 2], 0]).all()


def test_cat_bond_strategy_scales_between_floor_and_cap_with_richness() -> None:
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
            "cat_bond_richness": np.full((2, 1), 1.0),
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
        low_richness=[0.8],
        high_richness=[1.2],
    )

    assert result[0, 0] == 0.20
