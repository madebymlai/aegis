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


def _close(columns: tuple[str, ...], periods: int = 4) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=periods, freq="D")
    return pd.DataFrame(
        np.linspace(100.0, 103.0, periods)[:, None] * np.ones((1, len(columns))),
        index=index,
        columns=pd.Index(
            [InstrumentId.from_str(column) for column in columns],
            name="instrument_id",
        ),
    )


def test_putwrite_indicator_scores_credit_but_not_packaged_putwrite(monkeypatch) -> None:
    component = _load(
        "research/components/indicators/demeter/demeter_carry_putwrite.py",
        "demeter_carry_putwrite_test",
    )
    close = _close(("SDHY.LSEETF", "LQDH.LSEETF", "E50PW.EBS"))
    fred_index = pd.date_range("2024-01-01", periods=4, freq="D")
    series = {
        component._BAA: pd.Series([6.0, 6.2, 6.4, 6.6], index=fred_index),
        component._UST10: pd.Series([4.0, 4.0, 4.0, 4.0], index=fred_index),
    }
    monkeypatch.setattr(component, "_fred_series", series.__getitem__)

    result = component.run(
        MarketDataBundle(arrays={"Close": close}),
        n_candidates=1,
        carry_window=[2],
    )["carry_score"]

    assert np.isfinite(result[2:, :2]).all()
    assert np.isnan(result[:, 2]).all()


def _putwrite_strategy_case(putwrite_weight: float) -> np.ndarray:
    component = _load(
        "research/components/strategies/demeter/carry_putwrite.py",
        "demeter_carry_putwrite_strategy_test",
    )
    close = _close(("SDHY.LSEETF", "LQDH.LSEETF", "E50PW.EBS"))
    data = MarketDataBundle(arrays={"Close": close})
    carry_score = np.tile(np.array([[1.0, 1.0, np.nan]]), (4, 1))
    realized_vol = np.tile(np.array([[0.10, 0.10, 0.10]]), (4, 1))
    inputs = ComponentStrategyInputs(
        data=data,
        indicators={"carry_score": carry_score, "realized_vol": realized_vol},
        n_candidates=1,
        n_symbols=3,
        metadata={},
    )
    common = {
        "vol_target": [0.10],
        "defensive": [1.0],
        "fx_weight": [0.0],
        "carry_gain": [0.0],
        "at1_weight": [0.0],
    }

    return component.run(
        inputs,
        n_candidates=1,
        putwrite_weight=[putwrite_weight],
        **common,
    )


def test_putwrite_strategy_zero_weight_is_nested_control() -> None:
    control = _putwrite_strategy_case(0.0)

    np.testing.assert_allclose(control[-1], [0.5, 0.5, 0.0])


def test_putwrite_strategy_assigns_positive_weight_explicitly() -> None:
    challenger = _putwrite_strategy_case(0.20)

    np.testing.assert_allclose(challenger[-1], [0.4, 0.4, 0.2])
