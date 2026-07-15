from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

_ROOT = Path(__file__).resolve().parents[3]
_INSTRUMENTS = (
    "SDIG.LSEETF",
    "LQDE.LSEETF",
    "SDHY.LSEETF",
    "IHYU.LSEETF",
)


def _load(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _close(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            InstrumentId.from_str(instrument): np.linspace(90.0, 91.0, len(index))
            for instrument in _INSTRUMENTS
        },
        index=index,
    )


def _credit_panel() -> pd.DataFrame:
    observations = [
        {
            "as_of_date": pd.Timestamp("2020-08-31"),
            "instrument_id": instrument,
            "available_at": pd.Timestamp("2020-09-01"),
            "excess_yield_proxy": value,
            "modified_duration": duration,
            "proxy_dts": value * duration,
            "coverage": coverage,
        }
        for instrument, value, duration, coverage in (
            ("SDIG.LSEETF", 0.56, 2.6, 0.95),
            ("LQDE.LSEETF", 1.92, 9.8, 0.99),
            ("SDHY.LSEETF", 3.82, 2.7, 0.98),
            ("IHYU.LSEETF", 3.88, 4.3, 0.99),
        )
    ]
    return pd.DataFrame(observations).set_index(["as_of_date", "instrument_id"])


def test_credit_indicator_publishes_month_end_analytics_on_the_next_session(
    tmp_path: Path, monkeypatch
) -> None:
    component = _load(
        "research/components/indicators/demeter/credit_bucket_yield.py",
        "demeter_credit_bucket_yield_test",
    )

    class Source:
        def __init__(self, cache_dir: Path) -> None:
            assert cache_dir == tmp_path

        def load_window(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            return _credit_panel()

    monkeypatch.setattr(component, "IsharesCreditSource", Source)
    close = _close(
        pd.DatetimeIndex(
            ["2020-08-31T00:00:00Z", "2020-09-01T00:00:00Z", "2020-09-02T00:00:00Z"]
        )
    )

    outputs = component.run(
        MarketDataBundle(arrays={"Close": close}),
        n_candidates=1,
        cache_dir=[str(tmp_path)],
        min_coverage=[0.90],
        max_age_days=[45],
    )

    assert np.isnan(outputs["credit_excess_yield_proxy"][0]).all()
    np.testing.assert_allclose(
        outputs["credit_excess_yield_proxy"][1], [0.56, 1.92, 3.82, 3.88]
    )
    np.testing.assert_allclose(outputs["credit_modified_duration"][1], [2.6, 9.8, 2.7, 4.3])
    np.testing.assert_allclose(
        outputs["credit_proxy_dts"][1], [1.456, 18.816, 10.314, 16.684]
    )
    np.testing.assert_array_equal(outputs["credit_data_fresh"][:, 0], [0.0, 1.0, 1.0])
    np.testing.assert_array_equal(outputs["credit_rebalance_due"][:, 0], [1.0, 1.0, 0.0])


def test_credit_indicator_rejects_a_bucket_below_the_coverage_contract(
    tmp_path: Path, monkeypatch
) -> None:
    component = _load(
        "research/components/indicators/demeter/credit_bucket_yield.py",
        "demeter_credit_bucket_low_coverage_test",
    )
    panel = _credit_panel()
    panel.loc[(pd.Timestamp("2020-08-31"), "SDIG.LSEETF"), "coverage"] = 0.89

    class Source:
        def __init__(self, cache_dir: Path) -> None:
            assert cache_dir == tmp_path

        def load_window(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            return panel

    monkeypatch.setattr(component, "IsharesCreditSource", Source)
    close = _close(pd.DatetimeIndex(["2020-09-01T00:00:00Z"]))

    outputs = component.run(
        MarketDataBundle(arrays={"Close": close}),
        n_candidates=1,
        cache_dir=[str(tmp_path)],
        min_coverage=[0.90],
        max_age_days=[45],
    )

    assert np.isnan(outputs["credit_excess_yield_proxy"][0, 0])
    assert outputs["credit_data_fresh"][0, 0] == 0.0


def test_credit_indicator_exposes_static_fallback_when_source_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    component = _load(
        "research/components/indicators/demeter/credit_bucket_yield.py",
        "demeter_credit_bucket_unavailable_test",
    )

    class Source:
        def __init__(self, cache_dir: Path) -> None:
            assert cache_dir == tmp_path

        def load_window(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            raise component.IsharesCreditDataError("offline and uncached")

    monkeypatch.setattr(component, "IsharesCreditSource", Source)
    close = _close(pd.DatetimeIndex(["2020-09-01T00:00:00Z"]))

    with pytest.warns(UserWarning, match="static fallback"):
        outputs = component.run(
            MarketDataBundle(arrays={"Close": close}),
            n_candidates=1,
            cache_dir=[str(tmp_path)],
            min_coverage=[0.90],
            max_age_days=[45],
        )

    assert np.isnan(outputs["credit_excess_yield_proxy"]).all()
    assert (outputs["credit_data_fresh"] == 0.0).all()
    assert (outputs["credit_rebalance_due"] == 1.0).all()


def _strategy_inputs(
    *,
    due: np.ndarray,
    excess_yield: np.ndarray,
    duration: np.ndarray,
    fresh: np.ndarray | None = None,
) -> ComponentStrategyInputs:
    periods = len(due)
    close = _close(pd.date_range("2020-09-01", periods=periods, freq="D"))
    live = np.ones_like(excess_yield) if fresh is None else fresh
    return ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={
            "credit_rebalance_due": due,
            "credit_excess_yield_proxy": excess_yield,
            "credit_modified_duration": duration,
            "credit_data_fresh": live,
        },
        n_candidates=1,
        n_symbols=4,
        metadata={},
    )


def test_static_credit_control_equally_weights_all_four_buckets() -> None:
    component = _load(
        "research/components/strategies/demeter/credit_yield_proxy_selector.py",
        "demeter_credit_static_test",
    )
    inputs = _strategy_inputs(
        due=np.ones((1, 4)),
        excess_yield=np.array([[4.5, 4.8, 6.5, 6.7]]),
        duration=np.array([[2.0, 8.0, 2.5, 4.0]]),
    )

    result = component.run(
        inputs,
        n_candidates=1,
        selection_strength=[0.0],
    )

    np.testing.assert_allclose(result[0], [0.25, 0.25, 0.25, 0.25])


def test_active_credit_portfolio_maximizes_proxy_at_static_duration() -> None:
    component = _load(
        "research/components/strategies/demeter/credit_yield_proxy_selector.py",
        "demeter_credit_active_test",
    )
    inputs = _strategy_inputs(
        due=np.ones((1, 4)),
        excess_yield=np.array([[5.0, 3.0, 4.0, 6.0]]),
        duration=np.array([[2.0, 6.0, 2.0, 4.0]]),
    )

    result = component.run(
        inputs,
        n_candidates=1,
        selection_strength=[1.0],
    )

    np.testing.assert_allclose(result[0], [0.35, 0.15, 0.05, 0.45])


def test_active_credit_selector_falls_back_to_static_when_one_bucket_is_unavailable() -> None:
    component = _load(
        "research/components/strategies/demeter/credit_yield_proxy_selector.py",
        "demeter_credit_fallback_test",
    )
    inputs = _strategy_inputs(
        due=np.ones((1, 4)),
        excess_yield=np.array([[np.nan, 4.8, 6.5, 6.7]]),
        duration=np.array([[np.nan, 8.0, 2.5, 4.0]]),
        fresh=np.array([[0.0, 1.0, 1.0, 1.0]]),
    )

    result = component.run(
        inputs,
        n_candidates=1,
        selection_strength=[1.0],
    )

    np.testing.assert_allclose(result[0], [0.25, 0.25, 0.25, 0.25])


def test_active_credit_selector_emits_targets_only_on_monthly_decisions() -> None:
    component = _load(
        "research/components/strategies/demeter/credit_yield_proxy_selector.py",
        "demeter_credit_monthly_test",
    )
    inputs = _strategy_inputs(
        due=np.array([[1.0] * 4, [0.0] * 4]),
        excess_yield=np.array([[5.0, 3.0, 4.0, 6.0], [5.0, 3.0, 4.0, 6.0]]),
        duration=np.array([[2.0, 6.0, 2.0, 4.0], [2.0, 6.0, 2.0, 4.0]]),
    )

    result = component.run(
        inputs,
        n_candidates=1,
        selection_strength=[1.0],
    )

    np.testing.assert_allclose(result[0], [0.35, 0.15, 0.05, 0.45])
    assert np.isnan(result[1]).all()
