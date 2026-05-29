from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle

_SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]


def _make_data(n_dates: int = 400) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(_SYMBOLS)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


class TestVanguardCarryScoreManifest:
    def test_manifest_keys(self) -> None:
        from research.components.indicators.vanguard_carry_score import (
            COMPONENT_CALLABLE,
            COMPONENT_MANIFEST,
        )

        assert COMPONENT_CALLABLE == "run"
        required_keys = {
            "family", "id", "version", "input_names", "param_names",
            "output_names", "defaults", "param_space_callable", "wide_callable",
        }
        assert required_keys <= set(COMPONENT_MANIFEST.keys())
        assert COMPONENT_MANIFEST["output_names"] == ["carry_score"]

    def test_param_space(self) -> None:
        from research.components.indicators.vanguard_carry_score import param_space

        space = param_space()
        assert set(space.keys()) == {"carry_window"}


class TestVanguardCarryScoreRun:
    def test_output_shape(self) -> None:
        from research.components.indicators.vanguard_carry_score import run

        data = _make_data()
        result = run(data, carry_window=252)
        assert result.shape == (400, len(_SYMBOLS))

    def test_warmup_rows_are_nan(self) -> None:
        from research.components.indicators.vanguard_carry_score import run

        data = _make_data()
        result = run(data, carry_window=252)
        assert result.iloc[:251].isna().all().all()

    def test_post_warmup_rows_are_not_nan(self) -> None:
        from research.components.indicators.vanguard_carry_score import run

        data = _make_data()
        result = run(data, carry_window=126)
        assert result.iloc[126:].isna().sum().sum() == 0

    def test_sign_convention(self) -> None:
        """Price below SMA should produce positive carry (cheap = buy signal)."""
        from research.components.indicators.vanguard_carry_score import run

        dates = pd.date_range("2023-01-01", periods=300, freq="D")
        prices = np.full((300, 2), 100.0)
        prices[260:, 0] = 90.0  # drop below SMA
        close = pd.DataFrame(prices, index=dates, columns=pd.Index(["A", "B"], name="symbol"))
        data = MarketDataBundle(features={"Close": close}, loaded_features=("Close",))
        result = run(data, carry_window=252)
        assert result["A"].iloc[-1] > 0, "price below SMA should yield positive carry"


class TestVanguardCarryScoreWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.vanguard_carry_score import run, run_wide

        data = _make_data()
        candidates = [{"carry_window": 126}, {"carry_window": 189}, {"carry_window": 252}]
        n_candidates = len(candidates)
        n_symbols = len(_SYMBOLS)

        param_lists = {"carry_window": [c["carry_window"] for c in candidates]}
        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (400, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10, equal_nan=True)
