from __future__ import annotations

import numpy as np
import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataBundle

_SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
_N_SYMBOLS = len(_SYMBOLS)


def _make_data(n_dates: int = 300) -> MarketDataBundle:
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, _N_SYMBOLS))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(prices, index=dates, columns=pd.Index(_SYMBOLS, name="symbol"))
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


class FakeInputs:
    """Minimal stand-in for ComponentStrategyInputs."""

    def __init__(self, data, indicators):
        self.data = data
        self.indicators = indicators


class FakeWideInputs:
    """Minimal stand-in for WideComponentStrategyInputs."""

    def __init__(self, data, indicators, n_candidates, n_symbols):
        self.data = data
        self.indicators = indicators
        self.n_candidates = n_candidates
        self.n_symbols = n_symbols


def _build_indicators(close, *, spy_positive=True, tlt_positive=True, all_positive=True):
    """Build synthetic indicator DataFrames.

    Parameters
    ----------
    spy_positive, tlt_positive : bool
        Control the sign of canary momentum scores to set the regime.
    all_positive : bool
        If False, all non-canary assets also get negative momentum.
    """

    T, n = close.shape
    mom_vals = np.full((T, n), 0.05 if all_positive else -0.05)
    col_list = list(close.columns)
    spy_idx = col_list.index("SPY")
    tlt_idx = col_list.index("TLT")
    mom_vals[:, spy_idx] = 0.10 if spy_positive else -0.10
    mom_vals[:, tlt_idx] = 0.08 if tlt_positive else -0.08

    momentum = pd.DataFrame(mom_vals, index=close.index, columns=close.columns)

    vol_vals = np.full((T, n), 0.15)
    vol = pd.DataFrame(vol_vals, index=close.index, columns=close.columns)

    return {"momentum_score": momentum, "realized_vol": vol}


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

class TestManifest:
    def test_manifest_required_keys(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import (
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
        assert COMPONENT_MANIFEST["id"] == "tests.momentum_rotator"
        assert COMPONENT_MANIFEST["output_name"] == "target_weights"
        assert COMPONENT_MANIFEST["owns_portfolio"] is False

    def test_param_space_returns_params(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import param_space

        space = param_space()
        assert set(space.keys()) == {"top_n", "top_k_defensive", "tau"}


# ---------------------------------------------------------------------------
# Risk-on regime
# ---------------------------------------------------------------------------

class TestRiskOnRegime:
    def test_only_offensive_assets_receive_weights(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        # Check a non-warmup bar
        row = result.iloc[-1]
        offensive_syms = {"IWM", "EEM", "GLD", "DBC", "VNQ", "XLE", "XLU"}

        # SPY and UUP should have zero weight in risk-on
        assert row.loc["SPY"] == 0.0
        assert row.loc["UUP"] == 0.0

        # At least some offensive assets should have positive weight
        off_weights = [row.loc[s] for s in offensive_syms]
        assert sum(w > 0 for w in off_weights) > 0

    def test_weights_sum_to_one(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        # Sum of last row should be ~1.0
        row = result.iloc[-1]
        non_nan = row.dropna()
        total = non_nan.sum()
        assert abs(total - 1.0) < 1e-10 or total == 0.0


# ---------------------------------------------------------------------------
# Risk-off regime
# ---------------------------------------------------------------------------

class TestRiskOffRegime:
    def test_only_defensive_assets_receive_weights(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=False, tlt_positive=False)
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        row = result.iloc[-1]
        offensive_only_syms = {"IWM", "EEM", "DBC", "VNQ", "XLE", "XLU"}

        # Offensive-only assets should be zero
        for sym in offensive_only_syms:
            assert row.loc[sym] == 0.0

        # SPY is canary-only, should be zero
        assert row.loc["SPY"] == 0.0

    def test_all_cash_when_defensive_momentum_negative(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        # All negative: canary negative -> risk-off, defensive also negative -> cash
        indicators = _build_indicators(
            close, spy_positive=False, tlt_positive=False, all_positive=False,
        )
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        row = result.iloc[-1]
        assert (row == 0.0).all()


# ---------------------------------------------------------------------------
# Mixed regime
# ---------------------------------------------------------------------------

class TestMixedRegime:
    def test_both_sleeves_receive_weights(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        # SPY positive, TLT negative -> mixed
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=False)
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        row = result.iloc[-1]

        # Offensive assets should have some weight (50% budget)
        offensive_syms = {"IWM", "EEM", "GLD", "DBC", "VNQ", "XLE", "XLU"}
        off_sum = sum(row.loc[s] for s in offensive_syms)

        # Defensive assets should have some weight (50% budget)
        # TLT has negative momentum so won't be selected; GLD and UUP are positive
        defensive_syms = {"TLT", "GLD", "UUP"}
        def_sum = sum(row.loc[s] for s in defensive_syms)

        assert off_sum > 0
        assert def_sum > 0

    def test_budgets_sum_to_one(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data()
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=False)
        inputs = FakeInputs(data, indicators)
        result = run(inputs, top_n=3, top_k_defensive=1, tau=0.0)

        row = result.iloc[-1]
        total = row.sum()
        # Should sum to at most 1.0 (could be less if some gated to cash)
        assert total <= 1.0 + 1e-10
        assert total > 0.0


# ---------------------------------------------------------------------------
# Turnover gate
# ---------------------------------------------------------------------------

class TestTurnoverGate:
    def test_high_tau_suppresses_rebalance(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data(n_dates=50)
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)
        inputs = FakeInputs(data, indicators)

        # tau=10.0 is impossibly high — after the first rebalance, turnover
        # from identical target weights is 0, so all subsequent bars are NaN
        result = run(inputs, top_n=3, top_k_defensive=1, tau=10.0)

        # First bar should have weights (no previous weights to compare)
        assert not np.isnan(result.iloc[0]).all()
        # Subsequent bars should be NaN (turnover < tau, regime unchanged)
        assert np.isnan(result.iloc[2]).all()
        assert np.isnan(result.iloc[10]).all()

    def test_regime_change_overrides_tau(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run

        data = _make_data(n_dates=50)
        close = data.feature("Close")
        indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)

        # Flip regime at bar 25: both canary negative → risk-off
        mom = indicators["momentum_score"].copy()
        col_list = list(close.columns)
        spy_idx = col_list.index("SPY")
        tlt_idx = col_list.index("TLT")
        mom.iloc[25:, spy_idx] = -0.10
        mom.iloc[25:, tlt_idx] = -0.08
        indicators["momentum_score"] = mom

        inputs = FakeInputs(data, indicators)
        # tau=10.0 would suppress all rebalances, but regime change overrides
        result = run(inputs, top_n=3, top_k_defensive=1, tau=10.0)

        assert not np.isnan(result.iloc[25]).all()


# ---------------------------------------------------------------------------
# run vs run_wide parity
# ---------------------------------------------------------------------------

class TestRunWideMatchesScalar:
    def test_parity_across_candidates(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run, run_wide

        data = _make_data()
        close = data.feature("Close")
        T = len(close)
        candidates = [
            {"top_n": 2, "top_k_defensive": 1, "tau": 0.0},
            {"top_n": 3, "top_k_defensive": 1, "tau": 0.08},
            {"top_n": 4, "top_k_defensive": 2, "tau": 0.15},
        ]
        n_candidates = len(candidates)

        # Build indicator arrays once
        base_indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)

        # --- scalar runs ---
        scalar_results = []
        for params in candidates:
            inputs = FakeInputs(data, base_indicators)
            scalar_results.append(run(inputs, **params).values)

        # --- wide run ---
        # Broadcast indicator DataFrames to wide numpy arrays
        wide_indicators = {}
        for key, df in base_indicators.items():
            arr = df.values  # (T, n_symbols)
            # Tile across candidates: (T, n_candidates * n_symbols)
            wide_indicators[key] = np.tile(arr, (1, n_candidates))

        wide_inputs = FakeWideInputs(
            data=data,
            indicators=wide_indicators,
            n_candidates=n_candidates,
            n_symbols=_N_SYMBOLS,
        )
        param_lists = {
            key: [c[key] for c in candidates]
            for key in ["top_n", "top_k_defensive", "tau"]
        }
        wide_result = run_wide(wide_inputs, n_candidates=n_candidates, **param_lists)
        wide_arr = np.asarray(wide_result)

        assert wide_arr.shape == (T, n_candidates * _N_SYMBOLS)

        for i, scalar_arr in enumerate(scalar_results):
            wide_slice = wide_arr[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)

    def test_duplicate_candidates(self) -> None:
        from tests.fixtures.components.strategies.tests_momentum_rotator import run, run_wide

        data = _make_data()
        close = data.feature("Close")
        params = {"top_n": 3, "top_k_defensive": 1, "tau": 0.0}

        base_indicators = _build_indicators(close, spy_positive=True, tlt_positive=True)
        inputs = FakeInputs(data, base_indicators)
        scalar_arr = run(inputs, **params).values

        wide_indicators = {}
        for key, df in base_indicators.items():
            wide_indicators[key] = np.tile(df.values, (1, 2))

        wide_inputs = FakeWideInputs(
            data=data,
            indicators=wide_indicators,
            n_candidates=2,
            n_symbols=_N_SYMBOLS,
        )
        wide_result = run_wide(
            wide_inputs,
            n_candidates=2,
            top_n=[3, 3],
            top_k_defensive=[1, 1],
            tau=[0.0, 0.0],
        )
        wide_arr = np.asarray(wide_result)

        for i in range(2):
            wide_slice = wide_arr[:, i * _N_SYMBOLS : (i + 1) * _N_SYMBOLS]
            np.testing.assert_allclose(wide_slice, scalar_arr, atol=1e-10)
