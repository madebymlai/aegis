from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle


def _make_data(n_dates: int = 300, symbols: list[str] | None = None) -> MarketDataBundle:
    symbols = symbols or ["SPY", "QQQ", "IWM", "TLT", "GLD"]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(symbols)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(symbols, name="symbol"))
    return MarketDataBundle(arrays={"Close": close})


def test_manifest_is_v2_domain_facts_only() -> None:
    from tests.fixtures.components.indicators.tests_momentum_score import COMPONENT_MANIFEST

    assert COMPONENT_MANIFEST["id"] == "tests.momentum_score"
    assert COMPONENT_MANIFEST["output_names"] == ["momentum_score"]
    assert "wide_callable" not in COMPONENT_MANIFEST
    assert "param_space_callable" not in COMPONENT_MANIFEST


def test_param_space_returns_params() -> None:
    from tests.fixtures.components.indicators.tests_momentum_score import param_space

    space = param_space()
    assert set(space) == {"h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"}


def test_run_returns_candidate_major_mapping() -> None:
    from tests.fixtures.components.indicators.tests_momentum_score import run

    data = _make_data()
    candidates = [
        {"h1": 21, "h2": 63, "h3": 126, "h4": 252, "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0},
        {"h1": 15, "h2": 42, "h3": 100, "h4": 200, "w1": 8.0, "w2": 2.0, "w3": 1.0, "w4": 0.5},
    ]
    param_lists = {key: [candidate[key] for candidate in candidates] for key in candidates[0]}

    result = run(data, n_candidates=len(candidates), **param_lists)

    arr = result["momentum_score"]
    assert arr.shape == (300, 2 * 5)
    assert np.isnan(arr[0]).all()
    assert np.isfinite(arr[252:]).all()
