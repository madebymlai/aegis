"""Math + contract tests for the shared EquityCurve read.

EquityCurve is the one-read-per-batch primitive every custom Metric derives
from. Its interface is the test surface for the drawdown / annualization /
benchmark-alignment math the metric readers used to each re-derive, so the math
gets tested once here instead of indirectly through five readers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.metrics.custom.support import EquityCurve


class _StubPortfolio:
    """Counts get_value reads so the one-read contract is an assertable property."""

    def __init__(self, value: pd.DataFrame | pd.Series, close: pd.DataFrame) -> None:
        self._value = value
        self.close = close
        self.get_value_calls = 0

    def get_value(self) -> pd.DataFrame | pd.Series:
        self.get_value_calls += 1
        return self._value


def _two_group_portfolio() -> _StubPortfolio:
    index = pd.date_range("2024-01-01", periods=5, freq="D")
    value = pd.DataFrame(
        {"a": [100.0, 110.0, 99.0, 120.0, 108.0], "b": [100.0, 100.0, 100.0, 100.0, 100.0]},
        index=index,
    )
    value.columns = pd.Index(["a", "b"], name="candidate_id")
    groups = value.columns
    spy = pd.Series([100.0, 102.0, 99.0, 101.0, 100.0], index=index)
    close_columns = pd.MultiIndex.from_product(
        [groups, ["SPY", "TLT"]], names=["candidate_id", SYMBOL_LEVEL]
    )
    close = pd.DataFrame(
        {col: (spy if col[1] == "SPY" else pd.Series(50.0, index=index)) for col in close_columns}
    )
    close.columns = close_columns
    return _StubPortfolio(value, close)


def test_from_portfolio_reads_value_exactly_once() -> None:
    pf = _two_group_portfolio()
    EquityCurve.from_portfolio(pf)
    assert pf.get_value_calls == 1


def test_from_portfolio_normalizes_a_series_to_a_frame() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    series = pd.Series([100.0, 105.0, 102.0], index=index, name="only")
    close = pd.DataFrame(
        {("only", "SPY"): [10.0, 11.0, 10.5]},
        index=index,
    )
    close.columns = pd.MultiIndex.from_tuples(
        [("only", "SPY")], names=["candidate_id", SYMBOL_LEVEL]
    )
    curve = EquityCurve.from_portfolio(_StubPortfolio(series, close))
    assert isinstance(curve.value, pd.DataFrame)
    assert list(curve.value.columns) == ["only"]


def test_drawdown_curve_is_value_over_running_peak() -> None:
    curve = EquityCurve.from_portfolio(_two_group_portfolio())
    drawdown = curve.drawdown_curve()
    # group "a" peaks at 110 on bar 1, troughs at 99 on bar 2 -> 99/110 - 1.
    assert drawdown["a"].iloc[2] == pytest.approx(99.0 / 110.0 - 1.0)
    # group "b" is flat -> never below its peak.
    assert (drawdown["b"] == 0.0).all()


def test_annualized_return_matches_geometric_growth() -> None:
    curve = EquityCurve.from_portfolio(_two_group_portfolio())
    annualized = curve.annualized_return(252)
    growth = 108.0 / 100.0  # group "a": last / first
    assert annualized["a"] == pytest.approx(growth ** (252 / 5) - 1.0)
    assert annualized["b"] == pytest.approx(0.0)


def test_returns_are_simple_pct_change() -> None:
    curve = EquityCurve.from_portfolio(_two_group_portfolio())
    returns = curve.returns()
    assert returns["a"].iloc[1] == pytest.approx(0.10)
    assert np.isnan(returns["a"].iloc[0])


def test_benchmark_returns_align_to_candidate_columns() -> None:
    curve = EquityCurve.from_portfolio(_two_group_portfolio())
    benchmark = curve.benchmark_returns("SPY")
    # Relabelled to the value frame's Candidate columns, identical content per group.
    assert list(benchmark.columns) == ["a", "b"]
    assert benchmark["a"].iloc[1] == pytest.approx(0.02)
    pd.testing.assert_series_equal(benchmark["a"], benchmark["b"], check_names=False)
