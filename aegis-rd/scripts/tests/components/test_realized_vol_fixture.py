from __future__ import annotations

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _make_data(n_dates: int = 120, instruments: list[InstrumentId] | None = None) -> MarketDataBundle:
    instruments = instruments or [_id("SPY.XNAS"), _id("QQQ.XNAS"), _id("IWM.XNAS")]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0002, 0.01, size=(n_dates, len(instruments)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(instruments, name="instrument_id"))
    return MarketDataBundle(arrays={"Close": close})


def test_manifest_is_v2_domain_facts_only() -> None:
    from tests.fixtures.components.indicators.tests_realized_vol import COMPONENT_MANIFEST

    assert COMPONENT_MANIFEST["id"] == "tests.realized_vol"
    assert COMPONENT_MANIFEST["output_names"] == ["realized_vol"]
    assert "wide_callable" not in COMPONENT_MANIFEST
    assert "param_space_callable" not in COMPONENT_MANIFEST


def test_param_space_returns_window_param() -> None:
    from tests.fixtures.components.indicators.tests_realized_vol import param_space

    assert set(param_space()) == {"window"}


def test_run_returns_candidate_major_mapping() -> None:
    from tests.fixtures.components.indicators.tests_realized_vol import run

    data = _make_data()
    result = run(data, n_candidates=2, window=[10, 20])

    arr = result["realized_vol"]
    assert arr.shape == (120, 2 * 3)
    assert np.isnan(arr[0]).all()
    assert np.isfinite(arr[20:]).all()
