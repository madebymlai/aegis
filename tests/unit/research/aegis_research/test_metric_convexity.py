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

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.custom.convexity import (
    BEAR_REGIME_BETA_ID,
    CRISIS_CONDITIONAL_RETURN_ID,
    QUARTERLY_SKEW_ID,
    TM_CONVEXITY_ID,
    TM_LINEAR_BETA_ID,
    convexity_metrics,
)

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
    assert vals[TM_LINEAR_BETA_ID]["mirror"] == pytest.approx(1.0, abs=1e-6)
    assert vals[TM_CONVEXITY_ID]["mirror"] == pytest.approx(0.0, abs=1e-6)
    assert vals[BEAR_REGIME_BETA_ID]["mirror"] == pytest.approx(1.0, abs=1e-6)
    # It loses with the benchmark on its worst days.
    assert vals[CRISIS_CONDITIONAL_RETURN_ID]["mirror"] < 0.0


def test_convex_is_the_long_gamma_pole() -> None:
    vals = _read_all()
    # Pure quadratic stream: positive convexity, ~zero linear beta.
    assert vals[TM_CONVEXITY_ID]["convex"] > 0.0
    assert vals[TM_LINEAR_BETA_ID]["convex"] == pytest.approx(0.0, abs=1e-6)
    # Gains on the benchmark's worst days, and de-risks the bear regime (beta < 0).
    assert vals[CRISIS_CONDITIONAL_RETURN_ID]["convex"] > 0.0
    assert vals[BEAR_REGIME_BETA_ID]["convex"] < 0.0


def test_quarterly_skew_separates_the_poles() -> None:
    vals = _read_all()
    skew = vals[QUARTERLY_SKEW_ID]
    # The all-positive convex stream is right-skewed and more so than the mirror.
    assert skew["convex"] > 0.0
    assert skew["convex"] > skew["mirror"]
