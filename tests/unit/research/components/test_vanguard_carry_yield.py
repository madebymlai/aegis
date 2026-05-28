from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle


_SYMBOLS = ["SPY", "IWM", "TLT", "GLD"]
_N_SYMBOLS = len(_SYMBOLS)


def _make_data(n_dates: int = 300) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, _N_SYMBOLS))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    div_yield = np.array([0.015, 0.012, 0.025, 0.0])
    daily_div = div_yield / 252
    adj_factor = np.exp(np.cumsum(np.full((n_dates, _N_SYMBOLS), daily_div), axis=0))
    adj_close = close * adj_factor
    return MarketDataBundle(
        features={"Close": close, "Adj Close": adj_close},
        loaded_features=("Close", "Adj Close"),
    )


class TestCarryYieldManifest:
    def test_manifest_fields(self) -> None:
        from research.components.indicators.vanguard_carry_yield import COMPONENT_MANIFEST
        assert COMPONENT_MANIFEST["id"] == "vanguard.carry_yield"
        assert "Adj Close" in COMPONENT_MANIFEST["input_names"]
        assert COMPONENT_MANIFEST["output_names"] == ["carry_score"]

    def test_param_space(self) -> None:
        from research.components.indicators.vanguard_carry_yield import param_space
        ps = param_space()
        assert "carry_horizon" in ps


class TestCarryYieldCompute:
    def test_shape(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run
        data = _make_data()
        result = run(data, carry_horizon=252)
        assert result.shape == (300, _N_SYMBOLS)

    def test_warmup_nan(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run
        data = _make_data()
        result = run(data, carry_horizon=126)
        assert np.all(np.isnan(result.values[:126]))

    def test_post_warmup_not_nan(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run
        data = _make_data()
        result = run(data, carry_horizon=126)
        assert not np.all(np.isnan(result.values[126:]))

    def test_gold_near_zero(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run
        data = _make_data()
        result = run(data, carry_horizon=252)
        gld_idx = list(result.columns).index("GLD")
        gld_carry = result.values[252:, gld_idx]
        assert np.all(np.abs(gld_carry) < 0.001)

    def test_equity_positive(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run
        data = _make_data()
        result = run(data, carry_horizon=252)
        spy_idx = list(result.columns).index("SPY")
        spy_carry = result.values[252:, spy_idx]
        assert np.mean(spy_carry) > 0


class TestCarryYieldWideParity:
    def test_run_wide_matches_scalar(self) -> None:
        from research.components.indicators.vanguard_carry_yield import run, run_wide
        data = _make_data()
        horizons = [126, 189, 252]
        n_candidates = len(horizons)

        wide_result = run_wide(data, n_candidates=n_candidates, carry_horizon=horizons)
        assert wide_result.shape == (300, n_candidates * _N_SYMBOLS)

        for i, h in enumerate(horizons):
            scalar = run(data, carry_horizon=h).values
            wide_slice = wide_result[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]
            nan_mask = np.isnan(scalar) | np.isnan(wide_slice)
            assert (np.isnan(scalar) == np.isnan(wide_slice)).all()
            numeric = ~nan_mask
            if numeric.any():
                np.testing.assert_allclose(wide_slice[numeric], scalar[numeric], atol=1e-10)
