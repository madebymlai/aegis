from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.optimization.component_source import WideComponentStrategyInputs


def _make_data(n_dates: int = 200, symbols: list[str] | None = None) -> MarketDataBundle:
    symbols = symbols or ["SPY", "QQQ", "IWM", "TLT", "GLD"]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(symbols)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(symbols, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


def _indicator_arrays(data: MarketDataBundle, candidates: list[dict]) -> dict[str, np.ndarray]:
    from research.components.indicators.local_trend_ma import run_wide as trend_wide
    from research.components.indicators.local_volatility import run_wide as vol_wide
    from research.components.indicators.local_momentum import run_wide as mom_wide

    n = len(candidates)
    trend = trend_wide(data, n_candidates=n, **{
        "fast_window": [c["fast_window"] for c in candidates],
        "slow_window": [c["slow_window"] for c in candidates],
        "slope_window": [c["slope_window"] for c in candidates],
        "wtype": [c["wtype"] for c in candidates],
    })
    vol = vol_wide(data, n_candidates=n, **{
        "window": [c["vol_window"] for c in candidates],
        "regime_window": [c["regime_window"] for c in candidates],
    })
    mom = mom_wide(data, n_candidates=n, **{
        "lookback": [c["lookback"] for c in candidates],
        "smooth_window": [c["smooth_window"] for c in candidates],
    })
    return {"trend_score": trend, "momentum_score": mom, "volatility_z": vol}


class TestEtfRotationWideParity:
    CANDIDATES = [
        {
            "fast_window": 10, "slow_window": 50, "slope_window": 3, "wtype": "simple",
            "vol_window": 20, "regime_window": 63, "lookback": 63, "smooth_window": 5,
            "top_n": 1, "rebalance_every": 1, "score_entry": 0.0,
            "volatility_ceiling": 2.0, "trend_weight": 5.0,
            "momentum_weight": 1.0, "volatility_weight": 0.25,
        },
        {
            "fast_window": 20, "slow_window": 100, "slope_window": 5, "wtype": "exp",
            "vol_window": 40, "regime_window": 126, "lookback": 42, "smooth_window": 3,
            "top_n": 2, "rebalance_every": 2, "score_entry": -0.05,
            "volatility_ceiling": 3.0, "trend_weight": 1.0,
            "momentum_weight": 2.0, "volatility_weight": 0.0,
        },
        {
            "fast_window": 40, "slow_window": 160, "slope_window": 10, "wtype": "simple",
            "vol_window": 10, "regime_window": 63, "lookback": 84, "smooth_window": 3,
            "top_n": 3, "rebalance_every": 5, "score_entry": 0.02,
            "volatility_ceiling": 1.5, "trend_weight": 2.0,
            "momentum_weight": 1.0, "volatility_weight": 0.02,
        },
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.local_trend_filter import run, run_wide
        from research.aegis_research.optimization.component_source import ComponentStrategyInputs

        data = _make_data()
        n_symbols = 5
        n_candidates = len(self.CANDIDATES)

        indicators = _indicator_arrays(data, self.CANDIDATES)

        wide_inputs = WideComponentStrategyInputs(
            data=data,
            indicators=indicators,
            n_candidates=n_candidates,
            n_symbols=n_symbols,
            metadata={},
        )
        strategy_params = {
            "top_n": [c["top_n"] for c in self.CANDIDATES],
            "rebalance_every": [c["rebalance_every"] for c in self.CANDIDATES],
            "score_entry": [c["score_entry"] for c in self.CANDIDATES],
            "volatility_ceiling": [c["volatility_ceiling"] for c in self.CANDIDATES],
            "trend_weight": [c["trend_weight"] for c in self.CANDIDATES],
            "momentum_weight": [c["momentum_weight"] for c in self.CANDIDATES],
            "volatility_weight": [c["volatility_weight"] for c in self.CANDIDATES],
        }
        wide_result = run_wide(wide_inputs, n_candidates=n_candidates, **strategy_params)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (200, n_candidates * n_symbols)

        for i, cand in enumerate(self.CANDIDATES):
            scalar_indicators = {}
            for key, arr in indicators.items():
                scalar_indicators[key] = pd.DataFrame(
                    arr[:, i * n_symbols : (i + 1) * n_symbols],
                    index=data.feature("Close").index,
                    columns=data.feature("Close").columns,
                )
            scalar_inputs = ComponentStrategyInputs(
                data=data,
                indicators=scalar_indicators,
                metadata={},
            )
            scalar_result = run(
                scalar_inputs,
                top_n=cand["top_n"],
                rebalance_every=cand["rebalance_every"],
                score_entry=cand["score_entry"],
                volatility_ceiling=cand["volatility_ceiling"],
                trend_weight=cand["trend_weight"],
                momentum_weight=cand["momentum_weight"],
                volatility_weight=cand["volatility_weight"],
            )
            # scalar returns True/False/NaN; convert to allocation weights
            scalar_df = scalar_result.copy()
            rebalance_mask = scalar_df.notna().any(axis=1)
            selected = scalar_df.loc[rebalance_mask].astype(bool)
            n_selected = selected.sum(axis=1).clip(lower=1)
            weights = selected.div(n_selected, axis=0).astype(float)
            expected = pd.DataFrame(
                np.nan, index=scalar_df.index, columns=scalar_df.columns
            )
            expected.loc[rebalance_mask] = weights
            expected_arr = expected.values

            wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]

            nan_mismatch = (np.isnan(wide_slice) != np.isnan(expected_arr)).sum()
            assert nan_mismatch == 0, f"candidate {i}: NaN position mismatch"

            numeric_mask = ~np.isnan(wide_slice) & ~np.isnan(expected_arr)
            if numeric_mask.any():
                np.testing.assert_allclose(
                    wide_slice[numeric_mask], expected_arr[numeric_mask], atol=1e-10,
                    err_msg=f"candidate {i}: numeric mismatch",
                )
