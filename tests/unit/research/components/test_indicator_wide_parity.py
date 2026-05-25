from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.market_data.contracts import MarketDataBundle


def _make_data(n_dates: int = 200, symbols: list[str] | None = None) -> MarketDataBundle:
    symbols = symbols or ["SPY", "QQQ", "IWM", "TLT", "GLD"]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(symbols)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(symbols, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


class TestTrendMaWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.local_trend_ma import run, run_wide

        data = _make_data()
        candidates = [
            {"fast_window": 10, "slow_window": 50, "slope_window": 3, "wtype": "simple"},
            {"fast_window": 20, "slow_window": 100, "slope_window": 5, "wtype": "exp"},
            {"fast_window": 40, "slow_window": 160, "slope_window": 10, "wtype": "simple"},
        ]
        n_candidates = len(candidates)
        n_symbols = 5

        param_lists = {
            "fast_window": [c["fast_window"] for c in candidates],
            "slow_window": [c["slow_window"] for c in candidates],
            "slope_window": [c["slope_window"] for c in candidates],
            "wtype": [c["wtype"] for c in candidates],
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (200, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)


class TestVolatilityWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.local_volatility import run, run_wide

        data = _make_data()
        candidates = [
            {"window": 10, "regime_window": 63},
            {"window": 20, "regime_window": 126},
            {"window": 40, "regime_window": 63},
        ]
        n_candidates = len(candidates)
        n_symbols = 5

        param_lists = {
            "window": [c["window"] for c in candidates],
            "regime_window": [c["regime_window"] for c in candidates],
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (200, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)


class TestMomentumWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.local_momentum import run, run_wide

        data = _make_data()
        candidates = [
            {"lookback": 42, "smooth_window": 3},
            {"lookback": 63, "smooth_window": 5},
            {"lookback": 84, "smooth_window": 3},
        ]
        n_candidates = len(candidates)
        n_symbols = 5

        param_lists = {
            "lookback": [c["lookback"] for c in candidates],
            "smooth_window": [c["smooth_window"] for c in candidates],
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (200, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)
