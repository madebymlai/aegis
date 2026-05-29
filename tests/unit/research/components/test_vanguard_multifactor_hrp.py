from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.optimization.component_source import (
    ComponentStrategyInputs,
    WideComponentStrategyInputs,
)

_SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
_N_SYMBOLS = len(_SYMBOLS)

_INDICATOR_DEFAULTS = {
    "h1": 21, "h2": 63, "h3": 126, "h4": 252,
    "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0,
    "window": 20, "carry_window": 252,
}


def _make_data(n_dates: int = 400) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, _N_SYMBOLS))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


def _compute_indicators_scalar(data, params):
    from research.components.indicators.vanguard_momentum_score import run as mom_run
    from research.components.indicators.vanguard_realized_vol import run as vol_run
    from research.components.indicators.vanguard_carry_score import run as carry_run

    mom = mom_run(data, h1=params["h1"], h2=params["h2"], h3=params["h3"], h4=params["h4"],
                  w1=params["w1"], w2=params["w2"], w3=params["w3"], w4=params["w4"])
    vol = vol_run(data, window=params["window"])
    carry = carry_run(data, carry_window=params["carry_window"])
    return {"momentum_score": mom, "realized_vol": vol, "carry_score": carry}


def _compute_indicators_wide(data, candidates):
    from research.components.indicators.vanguard_momentum_score import run_wide as mom_wide
    from research.components.indicators.vanguard_realized_vol import run_wide as vol_wide
    from research.components.indicators.vanguard_carry_score import run_wide as carry_wide

    n = len(candidates)
    mom = mom_wide(data, n_candidates=n, **{
        k: [c[k] for c in candidates] for k in ["h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"]
    })
    vol = vol_wide(data, n_candidates=n, **{"window": [c["window"] for c in candidates]})
    carry = carry_wide(data, n_candidates=n, **{"carry_window": [c["carry_window"] for c in candidates]})
    return {"momentum_score": mom, "realized_vol": vol, "carry_score": carry}


class TestV13WideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 2, "top_k_defensive": 1, "tau": 0.05, "momentum_factor_wt": 0.6, "corr_lookback": 42},
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.7, "corr_lookback": 63},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 1, "tau": 0.15, "momentum_factor_wt": 0.8, "corr_lookback": 126},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp import run, run_wide

        data = _make_data()
        n_candidates = len(self.CANDIDATES)
        indicators_wide = _compute_indicators_wide(data, self.CANDIDATES)

        wide_inputs = WideComponentStrategyInputs(
            data=data, indicators=indicators_wide,
            n_candidates=n_candidates, n_symbols=_N_SYMBOLS, metadata={},
        )
        strategy_params = {
            k: [c[k] for c in self.CANDIDATES]
            for k in ["top_n", "top_k_defensive", "tau", "momentum_factor_wt", "corr_lookback"]
        }
        wide_arr = np.asarray(run_wide(wide_inputs, n_candidates=n_candidates, **strategy_params))
        assert wide_arr.shape == (400, n_candidates * _N_SYMBOLS)

        for i, cand in enumerate(self.CANDIDATES):
            scalar_indicators = _compute_indicators_scalar(data, cand)
            scalar_inputs = ComponentStrategyInputs(data=data, indicators=scalar_indicators, metadata={})
            scalar_arr = run(scalar_inputs, top_n=cand["top_n"], top_k_defensive=cand["top_k_defensive"],
                            tau=cand["tau"], momentum_factor_wt=cand["momentum_factor_wt"],
                            corr_lookback=cand["corr_lookback"]).values
            wide_slice = wide_arr[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]
            nan_mismatch = (np.isnan(wide_slice) != np.isnan(scalar_arr)).sum()
            assert nan_mismatch == 0, f"candidate {i}: NaN position mismatch"
            numeric_mask = ~np.isnan(wide_slice) & ~np.isnan(scalar_arr)
            if numeric_mask.any():
                np.testing.assert_allclose(
                    wide_slice[numeric_mask], scalar_arr[numeric_mask], atol=1e-10,
                    err_msg=f"candidate {i}: numeric mismatch",
                )


class TestV14WideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 2, "top_k_defensive": 1, "tau": 0.05, "momentum_factor_wt": 0.6, "vol_target": 0.08},
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.7, "vol_target": 0.10},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 1, "tau": 0.15, "momentum_factor_wt": 0.8, "vol_target": 0.15},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_multifactor_voltarget import run, run_wide

        data = _make_data()
        n_candidates = len(self.CANDIDATES)
        indicators_wide = _compute_indicators_wide(data, self.CANDIDATES)

        wide_inputs = WideComponentStrategyInputs(
            data=data, indicators=indicators_wide,
            n_candidates=n_candidates, n_symbols=_N_SYMBOLS, metadata={},
        )
        strategy_params = {
            k: [c[k] for c in self.CANDIDATES]
            for k in ["top_n", "top_k_defensive", "tau", "momentum_factor_wt", "vol_target"]
        }
        wide_arr = np.asarray(run_wide(wide_inputs, n_candidates=n_candidates, **strategy_params))
        assert wide_arr.shape == (400, n_candidates * _N_SYMBOLS)

        for i, cand in enumerate(self.CANDIDATES):
            scalar_indicators = _compute_indicators_scalar(data, cand)
            scalar_inputs = ComponentStrategyInputs(data=data, indicators=scalar_indicators, metadata={})
            scalar_arr = run(scalar_inputs, top_n=cand["top_n"], top_k_defensive=cand["top_k_defensive"],
                            tau=cand["tau"], momentum_factor_wt=cand["momentum_factor_wt"],
                            vol_target=cand["vol_target"]).values
            wide_slice = wide_arr[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]
            nan_mismatch = (np.isnan(wide_slice) != np.isnan(scalar_arr)).sum()
            assert nan_mismatch == 0, f"candidate {i}: NaN position mismatch"
            numeric_mask = ~np.isnan(wide_slice) & ~np.isnan(scalar_arr)
            if numeric_mask.any():
                np.testing.assert_allclose(
                    wide_slice[numeric_mask], scalar_arr[numeric_mask], atol=1e-10,
                    err_msg=f"candidate {i}: numeric mismatch",
                )
