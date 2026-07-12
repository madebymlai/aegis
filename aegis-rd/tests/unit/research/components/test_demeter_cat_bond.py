from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
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
            "cat_bond_risk_multiple": np.full((4, 1), 4.0),
            "cat_bond_richness": np.full((4, 1), 0.7),
            "cat_bond_data_fresh": np.ones((4, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_multiple=[2.0],
    )

    np.testing.assert_allclose(result[[0, 3], 0], [0.7, 0.7])
    assert np.isnan(result[[1, 2], 0]).all()


def test_cat_bond_strategy_is_off_when_compensation_is_inadequate() -> None:
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
            "cat_bond_risk_multiple": np.full((2, 1), 1.9),
            "cat_bond_richness": np.full((2, 1), 0.7),
            "cat_bond_data_fresh": np.ones((2, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_multiple=[2.0],
    )

    assert result[0, 0] == 0.0


def test_cat_bond_strategy_is_off_without_fresh_market_data() -> None:
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
            "cat_bond_net_carry": np.full((1, 1), np.nan),
            "cat_bond_risk_multiple": np.full((1, 1), 3.5),
            "cat_bond_richness": np.full((1, 1), 0.7),
            "cat_bond_data_fresh": np.zeros((1, 1)),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_multiple=[2.0],
    )

    assert result[0, 0] == 0.0


@pytest.mark.parametrize(
    ("net_carry", "risk_multiple", "richness", "fresh", "expected"),
    [
        (5.74, 2.34, 0.3317, 1.0, 0.3317),
        (5.74, 2.00, 0.70, 1.0, 0.70),
        (5.74, 3.00, 1.00, 1.0, 1.00),
        (5.74, 1.99, 0.70, 1.0, 0.0),
        (0.00, 3.00, 0.70, 1.0, 0.0),
        (-0.01, 3.00, 0.70, 1.0, 0.0),
        (5.74, 3.00, 0.70, 0.0, 0.0),
        (5.74, 3.00, np.nan, 1.0, 0.0),
    ],
)
def test_cat_bond_sizing_uses_richness_within_its_sleeve(
    net_carry: float,
    risk_multiple: float,
    richness: float,
    fresh: float,
    expected: float,
) -> None:
    component = _load(
        "research/components/strategies/demeter/cat_bond_income.py",
        f"demeter_cat_bond_sizing_{net_carry}_{risk_multiple}_{fresh}",
    )
    close = _close(pd.date_range("2026-07-01", periods=1))
    inputs = ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={
            "rebalance_due": np.ones((1, 1)),
            "cat_bond_net_carry": np.array([[net_carry]]),
            "cat_bond_risk_multiple": np.array([[risk_multiple]]),
            "cat_bond_richness": np.array([[richness]]),
            "cat_bond_data_fresh": np.array([[fresh]]),
        },
        n_candidates=1,
        n_symbols=1,
        metadata={},
    )

    result = component.run(
        inputs,
        n_candidates=1,
        min_multiple=[2.0],
    )

    assert result[0, 0] == expected
