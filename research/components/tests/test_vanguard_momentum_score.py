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
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


class TestVanguardMomentumScoreManifest:
    def test_manifest_keys(self) -> None:
        from research.components.indicators.vanguard_momentum_score import (
            COMPONENT_CALLABLE,
            COMPONENT_MANIFEST,
        )

        assert COMPONENT_CALLABLE == "run"
        required_keys = {
            "family", "id", "version", "input_names", "param_names",
            "output_names", "defaults", "param_space_callable", "wide_callable",
        }
        assert required_keys <= set(COMPONENT_MANIFEST.keys())
        assert COMPONENT_MANIFEST["output_names"] == ["momentum_score"]
        assert COMPONENT_MANIFEST["id"] == "vanguard.momentum_score"

    def test_param_space_returns_params(self) -> None:
        from research.components.indicators.vanguard_momentum_score import param_space

        space = param_space()
        assert set(space.keys()) == {"h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"}


class TestVanguardMomentumScoreRun:
    def test_output_shape(self) -> None:
        from research.components.indicators.vanguard_momentum_score import run

        data = _make_data()
        result = run(data, h1=21, h2=63, h3=126, h4=252, w1=12.0, w2=4.0, w3=2.0, w4=1.0)
        assert result.shape == (300, 5)

    def test_warmup_is_nan_then_real_values(self) -> None:
        from research.components.indicators.vanguard_momentum_score import run

        data = _make_data()
        result = run(data, h1=21, h2=63, h3=126, h4=252, w1=12.0, w2=4.0, w3=2.0, w4=1.0)
        assert result.iloc[0].isna().all()
        assert result.iloc[252:].notna().all().all()


class TestVanguardMomentumScoreWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.vanguard_momentum_score import run, run_wide

        data = _make_data()
        candidates = [
            {"h1": 21, "h2": 63, "h3": 126, "h4": 252, "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0},
            {"h1": 15, "h2": 42, "h3": 100, "h4": 200, "w1": 8.0, "w2": 2.0, "w3": 1.0, "w4": 0.5},
            {"h1": 30, "h2": 84, "h3": 180, "h4": 300, "w1": 16.0, "w2": 6.0, "w3": 3.0, "w4": 2.0},
        ]
        n_candidates = len(candidates)
        n_symbols = 5

        param_lists = {
            key: [c[key] for c in candidates]
            for key in ["h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"]
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (300, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)

    def test_run_wide_duplicate_candidates(self) -> None:
        """Duplicate param combos should produce identical slices."""
        from research.components.indicators.vanguard_momentum_score import run, run_wide

        data = _make_data()
        params = {"h1": 21, "h2": 63, "h3": 126, "h4": 252, "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0}
        candidates = [params, params]
        n_candidates = 2
        n_symbols = 5

        param_lists = {
            key: [c[key] for c in candidates]
            for key in ["h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"]
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        scalar_result = run(data, **params)
        scalar_arr = scalar_result.values

        for i in range(n_candidates):
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)
