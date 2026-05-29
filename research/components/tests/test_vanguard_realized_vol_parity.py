from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle


def _make_data(n_dates: int = 200, symbols: list[str] | None = None) -> MarketDataBundle:
    symbols = symbols or ["SPY", "QQQ", "IWM", "TLT", "GLD"]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(symbols)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(symbols, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


class TestVanguardRealizedVolWideParity:
    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.indicators.vanguard_realized_vol import run, run_wide

        data = _make_data()
        candidates = [
            {"window": 10},
            {"window": 20},
            {"window": 40},
        ]
        n_candidates = len(candidates)
        n_symbols = 5

        param_lists = {
            "window": [c["window"] for c in candidates],
        }

        wide_result = run_wide(data, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (200, n_candidates * n_symbols)

        for i, params in enumerate(candidates):
            scalar_result = run(data, **params)
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)

    def test_post_warmup_non_negative(self) -> None:
        from research.components.indicators.vanguard_realized_vol import run

        data = _make_data()
        result = run(data, window=20)
        post_warmup = result.iloc[21:]
        assert (post_warmup >= 0.0).all().all()

    def test_warmup_nan_then_real_values(self) -> None:
        from research.components.indicators.vanguard_realized_vol import run

        data = _make_data()
        result = run(data, window=20)
        assert result.iloc[0].isna().all()
        assert (result.iloc[21] > 0.0).all()

    def test_duplicate_candidates_produce_identical_columns(self) -> None:
        from research.components.indicators.vanguard_realized_vol import run_wide

        data = _make_data()
        n_symbols = 5
        wide_result = run_wide(
            data,
            n_candidates=2,
            window=[20, 20],
        )
        wide_arr = np.asarray(wide_result)
        np.testing.assert_array_equal(
            wide_arr[:, :n_symbols],
            wide_arr[:, n_symbols:],
        )
