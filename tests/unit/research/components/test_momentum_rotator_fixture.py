from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle

_SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]


class FakeComponentInputs:
    def __init__(self, data, indicators, n_candidates, n_symbols):
        self.data = data
        self.indicators = indicators
        self.n_candidates = n_candidates
        self.n_symbols = n_symbols


def _make_data(n_dates: int = 120) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(_SYMBOLS)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    return MarketDataBundle(features={"Close": close})


def _indicator_array(close: pd.DataFrame, n_candidates: int, value: float) -> np.ndarray:
    base = np.full(close.shape, value)
    result = np.full((len(close), n_candidates * len(close.columns)), np.nan)
    for i in range(n_candidates):
        result[:, i * len(close.columns) : (i + 1) * len(close.columns)] = base
    return result


def test_manifest_is_v2_domain_facts_only() -> None:
    from tests.fixtures.components.strategies.tests_momentum_rotator import COMPONENT_MANIFEST

    assert COMPONENT_MANIFEST["id"] == "tests.momentum_rotator"
    assert COMPONENT_MANIFEST["output_name"] == "target_weights"
    assert COMPONENT_MANIFEST["owns_portfolio"] is False
    assert "wide_callable" not in COMPONENT_MANIFEST
    assert "param_space_callable" not in COMPONENT_MANIFEST


def test_param_space_returns_params() -> None:
    from tests.fixtures.components.strategies.tests_momentum_rotator import param_space

    assert set(param_space()) == {"top_n", "top_k_defensive", "tau"}


def test_run_returns_candidate_major_allocation_array() -> None:
    from tests.fixtures.components.strategies.tests_momentum_rotator import run

    data = _make_data()
    close = data.feature("Close")
    n_candidates = 2
    inputs = FakeComponentInputs(
        data,
        {
            "momentum_score": _indicator_array(close, n_candidates, 0.05),
            "realized_vol": _indicator_array(close, n_candidates, 0.15),
        },
        n_candidates=n_candidates,
        n_symbols=len(close.columns),
    )

    result = run(
        inputs,
        n_candidates=n_candidates,
        top_n=[2, 3],
        top_k_defensive=[1, 2],
        tau=[0.0, 0.0],
    )

    assert result.shape == (120, n_candidates * len(close.columns))
    assert np.isfinite(result).any()
