from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import load_run_config
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

_ROOT = Path(__file__).resolve().parents[3]
_INDICATOR = "research/components/indicators/demeter/concave_payer_policy.py"
_STRATEGY = "research/components/strategies/demeter/insurance_credit_income.py"
_CONFIG = "research/configs/demeter/insurance_credit_income.yaml"


def _load(relative_path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, _ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _close_frame(
    instruments: tuple[str, ...],
    *,
    prices: tuple[float, ...] = (100.0, 10.0, 100.0),
) -> pd.DataFrame:
    index = pd.date_range("2026-01-13", periods=3, freq="D")
    return pd.DataFrame(
        {
            InstrumentId.from_str(instrument): np.full(len(index), price)
            for instrument, price in zip(instruments, prices, strict=True)
        },
        index=index,
    )


def _allocation_for_prices(indicator, strategy, prices: tuple[float, ...]):
    instruments = ("STEA.LSEETF", "CATB.LSEETF", "CBUS5E.XBRU")
    data = MarketDataBundle(arrays={"Close": _close_frame(instruments, prices=prices)})
    inputs = ComponentStrategyInputs(
        data=data,
        indicators=indicator.run(data, n_candidates=1),
        n_candidates=1,
        n_symbols=3,
        metadata={},
    )
    return strategy.run(inputs, n_candidates=1)


def test_static_policy_assigns_the_declared_payer_weights() -> None:
    indicator = _load(_INDICATOR, "demeter_concave_payer_policy_weight_test")
    strategy = _load(_STRATEGY, "demeter_insurance_credit_income_weight_test")

    allocations = _allocation_for_prices(indicator, strategy, (100.0, 10.0, 100.0))

    np.testing.assert_allclose(
        allocations,
        [[0.4, 0.2, 0.4], [0.4, 0.2, 0.4], [0.4, 0.2, 0.4]],
    )


def test_static_policy_does_not_time_the_observed_price_path() -> None:
    indicator = _load(_INDICATOR, "demeter_concave_payer_policy_path_test")
    strategy = _load(_STRATEGY, "demeter_insurance_credit_income_path_test")

    calm = _allocation_for_prices(indicator, strategy, (100.0, 10.0, 100.0))
    shocked = _allocation_for_prices(indicator, strategy, (10_000.0, 0.01, 1.0))

    np.testing.assert_array_equal(calm, shocked)


def test_policy_indicator_rejects_an_unregistered_payer_universe() -> None:
    indicator = _load(_INDICATOR, "demeter_concave_payer_policy_rejection_test")
    data = MarketDataBundle(
        arrays={
            "Close": _close_frame(("CBUS5E.XBRU", "STEA.LSEETF", "XY7D.IBIS2"))
        }
    )

    with pytest.raises(
        indicator.UnsupportedConcavePayerUniverseError,
        match="unsupported payer universe",
    ):
        indicator.run(data, n_candidates=1)


def test_config_resolves_the_payer_component_contract() -> None:
    registry = discover_component_registry(
        root=_ROOT / "research/components",
        repo_root=_ROOT,
    )

    resolved = load_run_config(_ROOT / _CONFIG, component_registry=registry)

    assert (
        resolved.config.data.instruments,
        [item.id for item in resolved.config.indicators],
        resolved.config.strategy.id,
    ) == (
        ["CBUS5E.XBRU", "STEA.LSEETF", "CATB.LSEETF"],
        ["demeter.concave_payer_policy"],
        "demeter.insurance_credit_income",
    )
