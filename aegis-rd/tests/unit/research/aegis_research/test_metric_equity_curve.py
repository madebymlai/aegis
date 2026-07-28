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
from research.aegis_research.metrics.custom.support.equity_curve import _scalar_bound


class _StubPortfolio:
    """Counts get_value reads so the one-read contract is an assertable property."""

    def __init__(
        self,
        value: pd.DataFrame | pd.Series,
        close: pd.DataFrame,
        *,
        sim_start: object = None,
        sim_end: object = None,
    ) -> None:
        self._value = value
        self.close = close
        self.sim_start = sim_start
        self.sim_end = sim_end
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


# --- Multi-candidate simulation-range bounds ---
# VBT returns Portfolio.sim_start / sim_end as a scalar for a single Candidate
# group but as a per-group Series once there is more than one group. EquityCurve
# slices its value frame with a single positional .iloc[start:end], which a Series
# bound crashes. The derived common-start contract guarantees every Candidate
# shares one scored range, so the per-group bounds collapse to the one shared
# scalar; a non-uniform bound is a contract violation and must raise.


def test_scalar_bound_reduces_uniform_series_to_int() -> None:
    assert _scalar_bound(pd.Series([3, 3, 3], index=["a", "b", "c"])) == 3
    assert _scalar_bound(np.array([5, 5])) == 5
    assert _scalar_bound(7) == 7
    assert _scalar_bound(None) is None


def test_scalar_bound_rejects_nonuniform_bounds() -> None:
    with pytest.raises(ValueError, match="one shared simulation bound"):
        _scalar_bound(pd.Series([3, 4], index=["a", "b"]))


def test_from_portfolio_collapses_per_group_series_bounds_to_scalar() -> None:
    pf = _two_group_portfolio()
    groups = pf.get_value().columns
    # VBT's multi-group shape: one bound value per Candidate group, all equal.
    pf.sim_start = pd.Series([2, 2], index=groups)
    pf.sim_end = pd.Series([5, 5], index=groups)
    curve = EquityCurve.from_portfolio(pf)
    assert curve.sim_start == 2 and isinstance(curve.sim_start, int)
    assert curve.sim_end == 5 and isinstance(curve.sim_end, int)


def test_multi_candidate_returns_equal_full_path_slice_and_stay_continuous() -> None:
    pf = _two_group_portfolio()
    full = pf.get_value()
    pf.sim_start = pd.Series([2, 2], index=full.columns)  # per-group (multi-candidate)
    curve = EquityCurve.from_portfolio(pf)
    # The batched (per-group Series) slice equals the full-path pct_change sliced
    # with the shared scalar start -- the known-good single-Candidate scalar path.
    expected = full.pct_change(fill_method=None).iloc[2:]
    pd.testing.assert_frame_equal(curve.returns(), expected)
    # The first in-range return is the CONTINUOUS transition (value[2]/value[1]-1),
    # not a return rebased against the portfolio's initial value.
    assert curve.returns()["a"].iloc[0] == pytest.approx(99.0 / 110.0 - 1.0)


def test_single_candidate_scalar_bound_passes_through_unchanged() -> None:
    pf = _two_group_portfolio()
    pf.sim_start = 2  # single-Candidate: VBT hands back a scalar, not a Series
    curve = EquityCurve.from_portfolio(pf)
    assert curve.sim_start == 2
    pd.testing.assert_frame_equal(
        curve.returns(), pf.get_value().pct_change(fill_method=None).iloc[2:]
    )
