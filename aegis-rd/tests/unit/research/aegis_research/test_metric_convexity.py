"""Sign/ordering tests for the convexity-axis verification metrics.

A benchmark *mirror* stream (returns equal the benchmark) is the concave,
long-biased pole; a *convex* stream (returns proportional to the squared
benchmark move) is the long-gamma pole. The metrics must separate them
the way the trend gate expects: convexity positive, crisis-conditional positive,
bear-regime beta negative, quarterly skew positive for the convex stream — and
the opposite signs for the mirror.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import research.aegis_research.metrics.custom.convexity as cx
from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.custom.convexity import (
    BEAR_MARKET_BETA_ID,
    CRASH_DAY_RETURN_ID,
    CRISIS_QUARTER_RETURN_ID,
    MARKET_BETA_ID,
    MARKET_CONVEXITY_ID,
    QUARTERLY_RETURN_SKEW_ID,
    convexity_metrics,
    crisis_payoff_bootstrap_ci_from_curve,
)
from research.aegis_research.metrics.custom.support import EquityCurve

_CONVEX_GAIN = 8.0


class _StubPortfolio:
    def __init__(self, value: pd.DataFrame, close: pd.DataFrame) -> None:
        self._value = value
        self.close = close

    def get_value(self) -> pd.DataFrame:
        return self._value


def _stub_portfolio() -> _StubPortfolio:
    """Two groups over ~2.5 years: a benchmark mirror and a convex stream.

    benchmark daily returns r_b drive both: ``mirror`` returns equal r_b (raw
    market beta 1, no convexity); ``convex`` returns equal 8*r_b**2 (pure
    quadratic — gains on any large move, most on the worst days).
    """
    index = pd.bdate_range("2021-01-04", periods=640)
    rng = np.random.default_rng(0)
    r_b = rng.normal(0.0003, 0.011, size=len(index))
    r_b[0] = 0.0

    spy_close = pd.Series(100.0 * np.cumprod(1.0 + r_b), index=index)
    mirror = pd.Series(10_000.0 * np.cumprod(1.0 + r_b), index=index)
    convex = pd.Series(10_000.0 * np.cumprod(1.0 + _CONVEX_GAIN * r_b**2), index=index)

    groups = pd.Index(["mirror", "convex"], name="candidate_id")
    value = pd.DataFrame({"mirror": mirror, "convex": convex})
    value.columns = groups

    close_columns = pd.MultiIndex.from_product(
        [groups, ["SPY", "TLT"]], names=["candidate_id", SYMBOL_LEVEL]
    )
    close = pd.DataFrame(
        {col: (spy_close if col[1] == "SPY" else pd.Series(50.0, index=index)) for col in close_columns}
    )
    close.columns = close_columns
    return _StubPortfolio(value, close)


def _read_all() -> dict[str, pd.Series]:
    pf = _stub_portfolio()
    config = ReportConfig()
    return {definition.id: spec.read(pf, config) for definition, spec in convexity_metrics("SPY")}


def test_mirror_is_the_concave_long_pole() -> None:
    vals = _read_all()
    # Returns equal the benchmark: raw market beta 1, no convexity, full bear beta.
    assert vals[MARKET_BETA_ID]["mirror"] == pytest.approx(1.0, abs=1e-6)
    assert vals[MARKET_CONVEXITY_ID]["mirror"] == pytest.approx(0.0, abs=1e-6)
    assert vals[BEAR_MARKET_BETA_ID]["mirror"] == pytest.approx(1.0, abs=1e-6)
    # It loses with the benchmark on its worst days, and over its worst quarters.
    assert vals[CRASH_DAY_RETURN_ID]["mirror"] < 0.0
    assert vals[CRISIS_QUARTER_RETURN_ID]["mirror"] < 0.0


def test_convex_is_the_long_gamma_pole() -> None:
    vals = _read_all()
    # Pure quadratic stream: positive convexity, ~zero linear beta.
    assert vals[MARKET_CONVEXITY_ID]["convex"] > 0.0
    assert vals[MARKET_BETA_ID]["convex"] == pytest.approx(0.0, abs=1e-6)
    # Gains on the benchmark's worst days, over its worst quarters, and de-risks the bear regime.
    assert vals[CRASH_DAY_RETURN_ID]["convex"] > 0.0
    assert vals[CRISIS_QUARTER_RETURN_ID]["convex"] > 0.0
    assert vals[BEAR_MARKET_BETA_ID]["convex"] < 0.0
    # The convex pole pays more over the benchmark's worst quarters than the long-biased mirror.
    assert vals[CRISIS_QUARTER_RETURN_ID]["convex"] > vals[CRISIS_QUARTER_RETURN_ID]["mirror"]


def test_crisis_payoff_bootstrap_ci_brackets_and_is_deterministic() -> None:
    curve = EquityCurve.from_portfolio(_stub_portfolio())
    ci = crisis_payoff_bootstrap_ci_from_curve(curve, "SPY")
    # Valid interval, and the always-positive convex pole's whole interval is non-negative.
    assert ci.loc["convex", "lower"] <= ci.loc["convex", "upper"]
    assert ci.loc["convex", "lower"] >= 0.0
    # Seeded, so the bound is deterministic across calls.
    pd.testing.assert_frame_equal(ci, crisis_payoff_bootstrap_ci_from_curve(curve, "SPY"))


def test_quarterly_skew_separates_the_poles() -> None:
    vals = _read_all()
    skew = vals[QUARTERLY_RETURN_SKEW_ID]
    # The all-positive convex stream is right-skewed and more so than the mirror.
    assert skew["convex"] > 0.0
    assert skew["convex"] > skew["mirror"]


def _stub_without_benchmark() -> tuple[_StubPortfolio, pd.Series]:
    """Same two streams, but the benchmark (SPY) is NOT a traded column.

    Returns the portfolio and the SPY close that must be sourced lazily; the close panel
    carries only TLT, so the metrics have to pull the benchmark to compute anything.
    """
    index = pd.bdate_range("2021-01-04", periods=640)
    rng = np.random.default_rng(0)
    r_b = rng.normal(0.0003, 0.011, size=len(index))
    r_b[0] = 0.0
    spy_close = pd.Series(100.0 * np.cumprod(1.0 + r_b), index=index)
    mirror = pd.Series(10_000.0 * np.cumprod(1.0 + r_b), index=index)
    convex = pd.Series(10_000.0 * np.cumprod(1.0 + _CONVEX_GAIN * r_b**2), index=index)

    groups = pd.Index(["mirror", "convex"], name="candidate_id")
    value = pd.DataFrame({"mirror": mirror, "convex": convex})
    value.columns = groups
    close_columns = pd.MultiIndex.from_product(
        [groups, ["TLT"]], names=["candidate_id", SYMBOL_LEVEL]
    )
    close = pd.DataFrame({col: pd.Series(50.0, index=index) for col in close_columns})
    close.columns = close_columns
    return _StubPortfolio(value, close), spy_close


def test_benchmark_pulled_lazily_when_not_in_book(monkeypatch: pytest.MonkeyPatch) -> None:
    """A benchmark absent from the traded panel is sourced lazily, giving identical signs."""
    pf, spy_close = _stub_without_benchmark()
    monkeypatch.setattr(cx, "_lazy_benchmark_close", lambda symbol, index: spy_close)
    config = ReportConfig()
    vals = {d.id: s.read(pf, config) for d, s in convexity_metrics("SPY")}
    # Same separation as the in-book case: mirror is the linear concave pole, convex the gamma pole.
    assert vals[MARKET_BETA_ID]["mirror"] == pytest.approx(1.0, abs=1e-6)
    assert vals[MARKET_CONVEXITY_ID]["mirror"] == pytest.approx(0.0, abs=1e-6)
    assert vals[MARKET_CONVEXITY_ID]["convex"] > 0.0
    assert vals[CRASH_DAY_RETURN_ID]["convex"] > 0.0


def test_unavailable_benchmark_degrades_to_nan_not_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the benchmark cannot be sourced, benchmark-relative metrics are NaN; skew still computes."""
    pf, _ = _stub_without_benchmark()

    def _boom(symbol: str, index: pd.DatetimeIndex) -> pd.Series:
        raise RuntimeError("offline")

    monkeypatch.setattr(cx, "_lazy_benchmark_close", _boom)
    config = ReportConfig()
    vals = {d.id: s.read(pf, config) for d, s in convexity_metrics("SPY")}
    assert np.isnan(vals[MARKET_CONVEXITY_ID]["mirror"])
    assert np.isnan(vals[CRASH_DAY_RETURN_ID]["convex"])
    # The intrinsic skew metric needs no benchmark and still classifies the poles.
    assert vals[QUARTERLY_RETURN_SKEW_ID]["convex"] > 0.0


def test_lazy_benchmark_close_conforms_tz_to_a_tz_aware_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lazily-pulled benchmark must carry the target index's tz.

    yf-sourced panels have a tz-aware (UTC) value index. The pulled close is reindexed onto that
    index downstream (``aligned_benchmark_returns``); a tz-naive benchmark index reindexes to
    all-NaN, silently NaN-ing every benchmark-relative metric. Regression for that mismatch: the
    conformed close must reindex onto a tz-aware target with no NaN gaps.
    """
    from vectorbtpro import vbt

    target = pd.bdate_range("2021-01-04", periods=10, tz="UTC")
    pulled = pd.Series(np.linspace(100.0, 110.0, len(target)), index=target)

    class _FakeData:
        @staticmethod
        def get(field: str) -> pd.Series:
            return pulled

    monkeypatch.setattr(vbt.YFData, "pull", lambda *args, **kwargs: _FakeData())
    cx._BENCHMARK_CACHE.clear()

    close = cx._lazy_benchmark_close("SPY", target)

    assert close.index.tz is not None
    assert close.reindex(target).notna().all()
    cx._BENCHMARK_CACHE.clear()
