from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.optimization.component_source import (
    ComponentStrategyInputs,
    WideComponentStrategyInputs,
)

_SYMBOLS_10 = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
_SYMBOLS_14 = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU", "XLF", "XLK", "TIP", "BWX"]

_INDICATOR_DEFAULTS = {
    "h1": 21, "h2": 63, "h3": 126, "h4": 252,
    "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0,
    "window": 20, "carry_window": 252,
}


def _make_data(n_dates: int = 400, symbols=None) -> MarketDataBundle:
    if symbols is None:
        symbols = _SYMBOLS_10
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(symbols)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(symbols, name="symbol"))
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


def _wide_parity_check(run_fn, run_wide_fn, candidates, strategy_param_names, data, n_symbols):
    n_candidates = len(candidates)
    n_dates = len(data.feature("Close"))
    indicators_wide = _compute_indicators_wide(data, candidates)

    wide_inputs = WideComponentStrategyInputs(
        data=data, indicators=indicators_wide,
        n_candidates=n_candidates, n_symbols=n_symbols, metadata={},
    )
    strategy_params = {
        k: [c[k] for c in candidates] for k in strategy_param_names
    }
    wide_arr = np.asarray(run_wide_fn(wide_inputs, n_candidates=n_candidates, **strategy_params))
    assert wide_arr.shape == (n_dates, n_candidates * n_symbols)

    for i, cand in enumerate(candidates):
        scalar_indicators = _compute_indicators_scalar(data, cand)
        scalar_inputs = ComponentStrategyInputs(data=data, indicators=scalar_indicators, metadata={})
        scalar_kwargs = {k: cand[k] for k in strategy_param_names}
        scalar_arr = run_fn(scalar_inputs, **scalar_kwargs).values
        wide_slice = wide_arr[:, i * n_symbols : (i + 1) * n_symbols]
        nan_mismatch = (np.isnan(wide_slice) != np.isnan(scalar_arr)).sum()
        assert nan_mismatch == 0, f"candidate {i}: NaN position mismatch"
        numeric_mask = ~np.isnan(wide_slice) & ~np.isnan(scalar_arr)
        if numeric_mask.any():
            np.testing.assert_allclose(
                wide_slice[numeric_mask], scalar_arr[numeric_mask], atol=1e-10,
                err_msg=f"candidate {i}: numeric mismatch",
            )


class TestV15Manifest:
    def test_manifest_fields(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_voltarget import COMPONENT_MANIFEST
        assert COMPONENT_MANIFEST["id"] == "vanguard.multifactorHrpVoltarget"
        assert "vol_target" in COMPONENT_MANIFEST["param_names"]
        assert "corr_lookback" in COMPONENT_MANIFEST["param_names"]

    def test_param_space(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_voltarget import param_space
        ps = param_space()
        assert "vol_target" in ps
        assert "corr_lookback" in ps


class TestV15WideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 2, "top_k_defensive": 1, "tau": 0.05, "momentum_factor_wt": 0.6, "corr_lookback": 42, "vol_target": 0.15},
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.5, "corr_lookback": 63, "vol_target": 0.20},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 1, "tau": 0.15, "momentum_factor_wt": 0.8, "corr_lookback": 42, "vol_target": 0.25},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_voltarget import run, run_wide
        data = _make_data()
        _wide_parity_check(
            run, run_wide, self.CANDIDATES,
            ["top_n", "top_k_defensive", "tau", "momentum_factor_wt", "corr_lookback", "vol_target"],
            data, len(_SYMBOLS_10),
        )


class TestV16Manifest:
    def test_manifest_fields(self) -> None:
        from research.components.strategies.vanguard_ensemble_mf import COMPONENT_MANIFEST
        assert COMPONENT_MANIFEST["id"] == "vanguard.ensembleMultifactor"
        assert "alpha" in COMPONENT_MANIFEST["param_names"]
        assert "corr_lookback" in COMPONENT_MANIFEST["param_names"]

    def test_param_space(self) -> None:
        from research.components.strategies.vanguard_ensemble_mf import param_space
        ps = param_space()
        assert "alpha" in ps
        assert "corr_lookback" in ps


class TestV16WideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 2, "top_k_defensive": 1, "tau": 0.05, "momentum_factor_wt": 0.6, "corr_lookback": 42, "alpha": 0.3},
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.5, "corr_lookback": 63, "alpha": 0.5},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 1, "tau": 0.15, "momentum_factor_wt": 0.8, "corr_lookback": 42, "alpha": 0.7},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_ensemble_mf import run, run_wide
        data = _make_data()
        _wide_parity_check(
            run, run_wide, self.CANDIDATES,
            ["top_n", "top_k_defensive", "tau", "momentum_factor_wt", "corr_lookback", "alpha"],
            data, len(_SYMBOLS_10),
        )


class TestV16AlphaBoundary:
    def test_alpha_zero_equals_v13(self) -> None:
        from research.components.strategies.vanguard_ensemble_mf import run as ens_run
        from research.components.strategies.vanguard_multifactor_hrp import run as v13_run

        data = _make_data()
        indicators = _compute_indicators_scalar(data, _INDICATOR_DEFAULTS)
        inputs = ComponentStrategyInputs(data=data, indicators=indicators, metadata={})

        params = {"top_n": 3, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.5, "corr_lookback": 63}
        ens_arr = ens_run(inputs, **params, alpha=0.0).values
        v13_arr = v13_run(inputs, **params).values

        nan_mask = ~np.isnan(ens_arr) & ~np.isnan(v13_arr)
        if nan_mask.any():
            np.testing.assert_allclose(ens_arr[nan_mask], v13_arr[nan_mask], atol=1e-10)


class TestV17Manifest:
    def test_manifest_fields(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_wide import COMPONENT_MANIFEST
        assert COMPONENT_MANIFEST["id"] == "vanguard.multifactorHrpWide"
        assert "corr_lookback" in COMPONENT_MANIFEST["param_names"]

    def test_param_space_expanded_ranges(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_wide import param_space
        ps = param_space()
        assert 5 in ps["top_n"].value
        assert 3 in ps["top_k_defensive"].value


class TestV17WideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 1, "tau": 0.05, "momentum_factor_wt": 0.6, "corr_lookback": 42},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 2, "tau": 0.10, "momentum_factor_wt": 0.5, "corr_lookback": 63},
        {**_INDICATOR_DEFAULTS, "top_n": 5, "top_k_defensive": 3, "tau": 0.15, "momentum_factor_wt": 0.8, "corr_lookback": 42},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_multifactor_hrp_wide import run, run_wide
        data = _make_data(symbols=_SYMBOLS_14)
        _wide_parity_check(
            run, run_wide, self.CANDIDATES,
            ["top_n", "top_k_defensive", "tau", "momentum_factor_wt", "corr_lookback"],
            data, len(_SYMBOLS_14),
        )
