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


def _make_data(n_dates: int = 400) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, _N_SYMBOLS))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


def _compute_indicators_scalar(data: MarketDataBundle, params: dict) -> dict[str, pd.DataFrame]:
    from research.components.indicators.vanguard_momentum_score import run as mom_run
    from research.components.indicators.vanguard_realized_vol import run as vol_run

    mom = mom_run(data, h1=params["h1"], h2=params["h2"], h3=params["h3"], h4=params["h4"],
                  w1=params["w1"], w2=params["w2"], w3=params["w3"], w4=params["w4"])
    vol = vol_run(data, window=params["window"])
    return {"momentum_score": mom, "realized_vol": vol}


def _compute_indicators_wide(
    data: MarketDataBundle, candidates: list[dict],
) -> dict[str, np.ndarray]:
    from research.components.indicators.vanguard_momentum_score import run_wide as mom_wide
    from research.components.indicators.vanguard_realized_vol import run_wide as vol_wide

    n = len(candidates)
    mom = mom_wide(data, n_candidates=n, **{
        k: [c[k] for c in candidates] for k in ["h1", "h2", "h3", "h4", "w1", "w2", "w3", "w4"]
    })
    vol = vol_wide(data, n_candidates=n, **{
        "window": [c["window"] for c in candidates],
    })
    return {"momentum_score": mom, "realized_vol": vol}


_INDICATOR_DEFAULTS = {
    "h1": 21, "h2": 63, "h3": 126, "h4": 252,
    "w1": 12.0, "w2": 4.0, "w3": 2.0, "w4": 1.0,
    "window": 20,
}


class TestVanguardEnsembleManifest:
    def test_manifest_keys(self) -> None:
        from research.components.strategies.vanguard_ensemble import (
            COMPONENT_CALLABLE,
            COMPONENT_MANIFEST,
        )

        assert COMPONENT_CALLABLE == "run"
        required_keys = {
            "family", "id", "version", "input_names", "param_names",
            "output_name", "consumes_outputs", "defaults",
            "param_space_callable", "owns_portfolio", "wide_callable",
        }
        assert required_keys <= set(COMPONENT_MANIFEST.keys())
        assert COMPONENT_MANIFEST["id"] == "vanguard.ensemble"
        assert "alpha" in COMPONENT_MANIFEST["param_names"]
        assert "vol_target" in COMPONENT_MANIFEST["param_names"]

    def test_param_space_returns_all_params(self) -> None:
        from research.components.strategies.vanguard_ensemble import param_space

        space = param_space()
        assert set(space.keys()) == {"top_n", "top_k_defensive", "tau", "vol_target", "alpha"}


class TestVanguardEnsembleWideParity:
    CANDIDATES = [
        {**_INDICATOR_DEFAULTS, "top_n": 2, "top_k_defensive": 1, "tau": 0.05, "vol_target": 0.10, "alpha": 0.3},
        {**_INDICATOR_DEFAULTS, "top_n": 3, "top_k_defensive": 2, "tau": 0.10, "vol_target": 0.12, "alpha": 0.5},
        {**_INDICATOR_DEFAULTS, "top_n": 4, "top_k_defensive": 1, "tau": 0.15, "vol_target": 0.08, "alpha": 0.7},
    ]

    def test_run_wide_matches_scalar_loop(self) -> None:
        from research.components.strategies.vanguard_ensemble import run, run_wide

        data = _make_data()
        n_candidates = len(self.CANDIDATES)
        indicators_wide = _compute_indicators_wide(data, self.CANDIDATES)

        wide_inputs = WideComponentStrategyInputs(
            data=data,
            indicators=indicators_wide,
            n_candidates=n_candidates,
            n_symbols=_N_SYMBOLS,
            metadata={},
        )
        strategy_params = {
            k: [c[k] for c in self.CANDIDATES]
            for k in ["top_n", "top_k_defensive", "tau", "vol_target", "alpha"]
        }
        wide_result = run_wide(wide_inputs, n_candidates=n_candidates, **strategy_params)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (400, n_candidates * _N_SYMBOLS)

        for i, cand in enumerate(self.CANDIDATES):
            scalar_indicators = _compute_indicators_scalar(data, cand)
            scalar_inputs = ComponentStrategyInputs(
                data=data, indicators=scalar_indicators, metadata={},
            )
            scalar_result = run(
                scalar_inputs,
                top_n=cand["top_n"],
                top_k_defensive=cand["top_k_defensive"],
                tau=cand["tau"],
                vol_target=cand["vol_target"],
                alpha=cand["alpha"],
            )
            scalar_arr = scalar_result.values
            wide_slice = wide_arr[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]

            nan_mismatch = (np.isnan(wide_slice) != np.isnan(scalar_arr)).sum()
            assert nan_mismatch == 0, f"candidate {i}: NaN position mismatch"

            numeric_mask = ~np.isnan(wide_slice) & ~np.isnan(scalar_arr)
            if numeric_mask.any():
                np.testing.assert_allclose(
                    wide_slice[numeric_mask], scalar_arr[numeric_mask], atol=1e-10,
                    err_msg=f"candidate {i}: numeric mismatch",
                )


class TestVanguardEnsembleAlphaBoundary:
    """At alpha=1.0 the ensemble should match standalone V1; at alpha=0.0, standalone V4."""

    def test_alpha_one_matches_v1(self) -> None:
        from research.components.strategies.vanguard_ensemble import run as ensemble_run
        from research.components.strategies.vanguard_momentum_rotator import run as v1_run

        data = _make_data()
        indicators = _compute_indicators_scalar(data, _INDICATOR_DEFAULTS)
        inputs = ComponentStrategyInputs(data=data, indicators=indicators, metadata={})

        params = {"top_n": 3, "top_k_defensive": 1, "tau": 0.08}
        v1_result = v1_run(inputs, **params).values
        ensemble_result = ensemble_run(
            inputs, **params, vol_target=0.10, alpha=1.0,
        ).values

        nan_mismatch = (np.isnan(v1_result) != np.isnan(ensemble_result)).sum()
        assert nan_mismatch == 0, "NaN position mismatch between ensemble(alpha=1) and V1"

        mask = ~np.isnan(v1_result) & ~np.isnan(ensemble_result)
        if mask.any():
            np.testing.assert_allclose(
                ensemble_result[mask], v1_result[mask], atol=1e-10,
            )

    def test_alpha_zero_matches_v4(self) -> None:
        from research.components.strategies.vanguard_ensemble import run as ensemble_run
        from research.components.strategies.vanguard_voltarget_rotator import run as v4_run

        data = _make_data()
        indicators = _compute_indicators_scalar(data, _INDICATOR_DEFAULTS)
        inputs = ComponentStrategyInputs(data=data, indicators=indicators, metadata={})

        params = {"top_n": 3, "top_k_defensive": 1, "tau": 0.08, "vol_target": 0.10}
        v4_result = v4_run(inputs, **params).values
        ensemble_result = ensemble_run(
            inputs, **params, alpha=0.0,
        ).values

        nan_mismatch = (np.isnan(v4_result) != np.isnan(ensemble_result)).sum()
        assert nan_mismatch == 0, "NaN position mismatch between ensemble(alpha=0) and V4"

        mask = ~np.isnan(v4_result) & ~np.isnan(ensemble_result)
        if mask.any():
            np.testing.assert_allclose(
                ensemble_result[mask], v4_result[mask], atol=1e-10,
            )
