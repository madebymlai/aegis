from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle
from research.aegis_research.external_data.ecb_fx import EcbUsdEurSource
from research.aegis_research.external_data.sec_cash_mergers import (
    SecCashMergerEventSource,
    SecFiling,
)
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

_ROOT = Path(__file__).resolve().parents[3]


def _load(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unexpected_network(*_args, **_kwargs):
    raise AssertionError("indicator attempted network access")


class _Filings:
    def filings(self, start, end):
        common = {
            "cik": "1001",
            "company_name": "Example Target Inc.",
            "symbol": "TGTX",
            "form": "8-K",
        }
        return [
            SecFiling(
                **common,
                accession="0001",
                filed_at="2026-01-06T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0001.txt",
                text="Agreement and Plan of Merger for $100.00 in cash per share.",
            ),
            SecFiling(
                **common,
                accession="0002",
                filed_at="2026-01-10T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0002.txt",
                text="Definitive merger agreement amended to $110.00 in cash per share.",
            ),
            SecFiling(
                **common,
                accession="0003",
                filed_at="2026-01-13T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0003.txt",
                text="The parties terminated the merger agreement.",
            ),
        ]


class _ProxyOnlyFilings:
    def filings(self, start, end):
        return [
            SecFiling(
                cik="1001",
                company_name="Example Target Inc.",
                symbol="TGTX",
                form="DEFM14A",
                accession="0001",
                filed_at="2026-01-06T16:00:00+00:00",
                source_url="https://www.sec.gov/Archives/edgar/data/1001/0001.txt",
                text="Agreement and Plan of Merger for $100.00 in cash per share.",
            )
        ]


class _Fx:
    def usd_per_eur(self, start, end):
        return pd.Series(1.0, index=pd.date_range(start, end, freq="D"))


def _deal_indicator_case(tmp_path, filings=None):
    events = tmp_path / "events"
    fx = tmp_path / "fx"
    event_source = SecCashMergerEventSource(events, client=filings or _Filings())
    event_source.sync(date(2026, 1, 1), date(2026, 1, 15))
    fx_source = EcbUsdEurSource(fx, client=_Fx())
    fx_source.sync(date(2026, 1, 1), date(2026, 1, 15))
    component = _load(
        "research/components/indicators/demeter/cash_merger_deal.py",
        "demeter_cash_merger_deal_behavior",
    )
    index = pd.date_range("2026-01-01", "2026-01-15", freq="D")
    close = pd.DataFrame(
        {
            InstrumentId.from_str("TGTX.XNAS"): [
                70,
                71,
                72,
                73,
                74,
                75,
                90,
                91,
                92,
                93,
                94,
                95,
                96,
                80,
                79,
            ],
            InstrumentId.from_str("SPY.ARCA"): np.linspace(500, 514, len(index)),
        },
        index=index,
    )
    params = {
        "event_cache_dir": [str(events)],
        "fx_cache_dir": [str(fx)],
        "filing_lag_days": [1],
        "break_lookback": [20],
        "completion_probability": [0.9],
        "default_close_days": [120],
        "roundtrip_cost_bps": [20.0],
        "min_expected_value_bps": [0.0],
        "benchmark_symbol": ["SPY"],
        "residual_lookback": [5],
        "news_exclusion_days": [2],
    }
    return component, MarketDataBundle({"Close": close}), params


def test_deal_indicator_reveals_terms_only_after_filings_and_stops_after_termination(
    tmp_path,
) -> None:
    component, data, params = _deal_indicator_case(tmp_path)

    result = component.run(
        data,
        n_candidates=1,
        **params,
    )

    assert result["deal_eligible"][5, 0] == 0.0
    assert result["deal_cash_offer"][6, 0] == 100.0
    assert result["deal_cash_offer"][10, 0] == 110.0
    assert result["deal_eligible"][13, 0] == 0.0
    assert result["deal_expected_value"][6, 0] > 0.0
    assert result["deal_annualized_spread"][6, 0] > 0.0


def test_deal_indicator_estimates_break_value_strictly_before_announcement(
    tmp_path,
) -> None:
    component, data, params = _deal_indicator_case(tmp_path)

    result = component.run(data, n_candidates=1, **params)

    assert result["deal_break_value"][6, 0] == 72.0


def test_deal_indicator_rejects_a_proxy_date_as_an_unaffected_price_anchor(
    tmp_path,
) -> None:
    component, data, params = _deal_indicator_case(tmp_path, _ProxyOnlyFilings())

    result = component.run(data, n_candidates=1, **params)

    assert np.isnan(result["deal_break_value"][6, 0])
    assert result["deal_eligible"][6, 0] == 0.0


def test_deal_indicator_reuses_covering_cache_without_network(tmp_path, monkeypatch) -> None:
    component, data, params = _deal_indicator_case(tmp_path)
    monkeypatch.setattr("requests.Session", _unexpected_network)
    monkeypatch.setattr("requests.get", _unexpected_network)

    result = component.run(data, n_candidates=1, **params)

    assert result["deal_cash_offer"][6, 0] == 100.0


def test_deal_indicator_configures_cache_locations_not_snapshot_files() -> None:
    component = _load(
        "research/components/indicators/demeter/cash_merger_deal.py",
        "demeter_cash_merger_deal_interface",
    )

    assert "event_snapshot_path" not in component.COMPONENT_MANIFEST["param_names"]
    assert "fx_snapshot_path" not in component.COMPONENT_MANIFEST["param_names"]
    assert component.COMPONENT_MANIFEST["defaults"]["event_cache_dir"].endswith(
        "research/data/cache/sec/cash-mergers"
    )
    assert component.COMPONENT_MANIFEST["defaults"]["fx_cache_dir"].endswith(
        "research/data/cache/ecb/eur-per-usd"
    )


def _strategy_inputs() -> ComponentStrategyInputs:
    index = pd.date_range("2026-01-01", periods=3)
    close = pd.DataFrame(
        np.full((3, 3), 100.0),
        index=index,
        columns=[InstrumentId.from_str(f"D{i}.XNAS") for i in range(3)],
    )
    return ComponentStrategyInputs(
        data=MarketDataBundle({"Close": close}),
        indicators={
            "deal_executable_price": np.full((3, 3), 100.0),
            "deal_expected_value": np.array([[3.0, 4.0, 2.0]] * 3),
            "deal_break_loss": np.array([[0.10, 0.20, 0.40]] * 3),
            "deal_eligible": np.ones((3, 3)),
            "deal_residual": np.array([[np.nan] * 3, [-0.03] * 3, [0.04] * 3]),
            "deal_news": np.zeros((3, 3)),
        },
        n_candidates=1,
        n_symbols=3,
        metadata={},
    )


def test_break_risk_strategy_equalizes_failure_contribution_and_deploys_the_sleeve() -> None:
    component = _load(
        "research/components/strategies/demeter/cash_merger_break_risk.py",
        "demeter_cash_merger_break_risk_behavior",
    )

    result = component.run(
        _strategy_inputs(),
        n_candidates=1,
        max_positions=[2],
        max_weight_multiple=[1.5],
        residual_entry_enabled=[False],
        residual_entry_threshold=[-0.02],
    ).reshape(3, 3)

    np.testing.assert_allclose(result[0], [2.0 / 3.0, 1.0 / 3.0, 0.0])
    np.testing.assert_allclose(result[0] * [0.10, 0.20, 0.40], [1.0 / 15.0, 1.0 / 15.0, 0.0])
    assert np.isclose(result[0].sum(), 1.0)


def test_break_risk_strategy_caps_relative_concentration_and_redistributes() -> None:
    component = _load(
        "research/components/strategies/demeter/cash_merger_break_risk.py",
        "demeter_cash_merger_break_risk_concentration_behavior",
    )
    inputs = _strategy_inputs()
    inputs.indicators["deal_break_loss"][:] = [0.01, 0.20, 0.20]

    result = component.run(
        inputs,
        n_candidates=1,
        max_positions=[3],
        max_weight_multiple=[1.5],
        residual_entry_enabled=[False],
        residual_entry_threshold=[-0.02],
    ).reshape(3, 3)

    np.testing.assert_allclose(result[0], [0.50, 0.25, 0.25])
    assert np.isclose(result[0].sum(), 1.0)


def test_break_risk_strategy_holds_cash_when_no_deal_is_eligible() -> None:
    component = _load(
        "research/components/strategies/demeter/cash_merger_break_risk.py",
        "demeter_cash_merger_break_risk_empty_behavior",
    )
    inputs = _strategy_inputs()
    inputs.indicators["deal_eligible"][:] = 0.0

    result = component.run(
        inputs,
        n_candidates=1,
        max_positions=[2],
        max_weight_multiple=[1.5],
        residual_entry_enabled=[False],
        residual_entry_threshold=[-0.02],
    ).reshape(3, 3)

    np.testing.assert_array_equal(result, np.zeros((3, 3)))


def test_residual_variant_only_delays_entry_and_does_not_requalify_events() -> None:
    component = _load(
        "research/components/strategies/demeter/cash_merger_break_risk.py",
        "demeter_cash_merger_residual_behavior",
    )

    result = component.run(
        _strategy_inputs(),
        n_candidates=1,
        max_positions=[2],
        max_weight_multiple=[1.5],
        residual_entry_enabled=[True],
        residual_entry_threshold=[-0.02],
    ).reshape(3, 3)

    np.testing.assert_array_equal(result[0], [0.0, 0.0, 0.0])
    np.testing.assert_allclose(result[1], [2.0 / 3.0, 1.0 / 3.0, 0.0])
    np.testing.assert_allclose(result[2], result[1])
