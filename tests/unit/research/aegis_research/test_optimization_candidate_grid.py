"""Unit tests for the Candidate Grid value object.

Covers construction/validation, the row-stack guard, the read surface,
parameter-sorted ordering, NaN-to-None normalization, non-rectangular grids,
and the shape-contract tests migrated from the validity test module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.optimization.candidate_grid import CandidateGrid

# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def _frame(
    tuples: list[tuple], *, names: list[str], columns: list[str]
) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(tuples, names=names)
    return pd.DataFrame(
        {col: [np.nan] * len(tuples) for col in columns}, index=index
    )


def _filled_frame(
    tuples: list[tuple],
    *,
    names: list[str],
    values: dict[str, list[float]],
) -> pd.DataFrame:
    index = pd.MultiIndex.from_tuples(tuples, names=names)
    return pd.DataFrame(values, index=index)


# ---------------------------------------------------------------------------
# Construction — valid
# ---------------------------------------------------------------------------


def test_constructs_from_valid_frame() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("A", "s1"), ("B", "s0"), ("B", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, 0.5, 0.3, 0.2]},
        )
    )
    assert grid.param_levels == ["param"]
    assert grid.metric_ids == ["sharpe"]


def test_constructs_multiple_param_levels() -> None:
    tuples = [("fast", "slow", "s0"), ("fast", "slow", "s1")]
    grid = CandidateGrid(
        _frame(tuples, names=["a", "b", "split"], columns=["x"])
    )
    assert grid.param_levels == ["a", "b"]


# ---------------------------------------------------------------------------
# Construction — validation errors
# ---------------------------------------------------------------------------


def test_rejects_non_multiindex() -> None:
    df = pd.DataFrame({"x": [1.0]}, index=[0])
    with pytest.raises(TypeError, match="MultiIndex"):
        CandidateGrid(df)


def test_rejects_missing_split_level() -> None:
    index = pd.MultiIndex.from_tuples([("A",)], names=["param"])
    df = pd.DataFrame({"x": [1.0]}, index=index)
    with pytest.raises(ValueError, match="split"):
        CandidateGrid(df)


def test_rejects_no_param_levels() -> None:
    index = pd.MultiIndex.from_tuples([("s0",)], names=["split"])
    df = pd.DataFrame({"x": [1.0]}, index=index)
    with pytest.raises(ValueError, match="parameter level"):
        CandidateGrid(df)


# ---------------------------------------------------------------------------
# from_sweep — row-stack guard
# ---------------------------------------------------------------------------


def test_from_sweep_rejects_non_dataframe() -> None:
    with pytest.raises(TypeError, match="DataFrame"):
        CandidateGrid.from_sweep(pd.Series([1.0]))  # type: ignore[arg-type]


def test_from_sweep_rejects_non_multiindex_dataframe() -> None:
    df = pd.DataFrame({"x": [1.0]})
    with pytest.raises(TypeError, match="MultiIndex"):
        CandidateGrid.from_sweep(df)


def test_from_sweep_normalizes_columns_name() -> None:
    df = pd.DataFrame(
        {"sharpe": [1.0]},
        index=pd.MultiIndex.from_tuples([("A", "s0")], names=["param", "split"]),
    )
    df.columns.name = "metrics"
    grid = CandidateGrid.from_sweep(df)
    assert grid.metric_ids == ["sharpe"]


def test_from_sweep_does_not_mutate_original() -> None:
    df = pd.DataFrame(
        {"sharpe": [1.0]},
        index=pd.MultiIndex.from_tuples([("A", "s0")], names=["param", "split"]),
    )
    df.columns.name = "metrics"
    CandidateGrid.from_sweep(df)
    # Original still has its columns name.
    assert df.columns.name == "metrics"


# ---------------------------------------------------------------------------
# by_candidate — read surface
# ---------------------------------------------------------------------------


def test_by_candidate_yields_all_candidates() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("A", "s1"), ("B", "s0"), ("B", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, 0.5, 0.3, 0.2]},
        )
    )
    keys = {key for key, _ in grid.by_candidate()}
    assert keys == {("A",), ("B",)}


def test_by_candidate_maps_split_to_metric_dict() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("A", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, 0.5], "max_dd": [-0.1, -0.2]},
        )
    )
    results = list(grid.by_candidate())
    assert len(results) == 1
    key, metrics = results[0]
    assert key == ("A",)
    assert metrics["s0"] == {"sharpe": 1.0, "max_dd": -0.1}
    assert metrics["s1"] == {"sharpe": 0.5, "max_dd": -0.2}


def test_by_candidate_parameter_sorted_order() -> None:
    """Iteration order is deterministic and parameter-sorted."""
    grid = CandidateGrid(
        _filled_frame(
            [
                ("c", "s0"), ("c", "s1"),
                ("a", "s0"), ("a", "s1"),
                ("b", "s0"), ("b", "s1"),
            ],
            names=["param", "split"],
            values={"sharpe": [1.0] * 6},
        )
    )
    keys = [key[0] for key, _ in grid.by_candidate()]
    assert keys == ["a", "b", "c"]


def test_by_candidate_multi_param_sorted_order() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [
                (2, "y", "s0"),
                (2, "y", "s1"),
                (1, "x", "s0"),
                (1, "x", "s1"),
            ],
            names=["a", "b", "split"],
            values={"sharpe": [1.0] * 4},
        )
    )
    keys = list(grid.by_candidate())
    # (1, "x") before (2, "y") by parameter-sorted grouping
    assert keys[0][0] == (1, "x")
    assert keys[1][0] == (2, "y")


# ---------------------------------------------------------------------------
# by_candidate — NaN-to-None normalization
# ---------------------------------------------------------------------------


def test_by_candidate_normalizes_nan_to_none() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("A", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, float("nan")]},
        )
    )
    _, metrics = next(grid.by_candidate())
    assert metrics["s0"]["sharpe"] == 1.0
    assert metrics["s1"]["sharpe"] is None


def test_by_candidate_preserves_real_zero() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0")],
            names=["param", "split"],
            values={"sharpe": [0.0]},
        )
    )
    _, metrics = next(grid.by_candidate())
    assert metrics["s0"]["sharpe"] == 0.0


def test_by_candidate_normalizes_inf() -> None:
    """Inf is not NaN, so it stays as float inf."""
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0")],
            names=["param", "split"],
            values={"sharpe": [float("inf")]},
        )
    )
    _, metrics = next(grid.by_candidate())
    assert metrics["s0"]["sharpe"] == float("inf")


# ---------------------------------------------------------------------------
# by_candidate — non-rectangular grids
# ---------------------------------------------------------------------------


def test_by_candidate_non_rectangular_grid() -> None:
    """Some candidates may not appear on every split."""
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("B", "s0"), ("B", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, 0.5, 0.3]},
        )
    )
    results = dict(grid.by_candidate())
    assert set(results[("A",)].keys()) == {"s0"}
    assert set(results[("B",)].keys()) == {"s0", "s1"}


# ---------------------------------------------------------------------------
# split_metrics — point lookup
# ---------------------------------------------------------------------------


def test_split_metrics_returns_same_shape() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0"), ("A", "s1"), ("B", "s0"), ("B", "s1")],
            names=["param", "split"],
            values={"sharpe": [1.0, 0.5, 0.3, 0.2]},
        )
    )
    for key, expected in grid.by_candidate():
        assert grid.split_metrics(key) == expected


def test_split_metrics_multi_param_key() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [(1, "x", "s0"), (1, "x", "s1"), (2, "y", "s0")],
            names=["a", "b", "split"],
            values={"sharpe": [1.0, 0.5, 0.3]},
        )
    )
    metrics = grid.split_metrics((1, "x"))
    assert metrics["s0"]["sharpe"] == 1.0
    assert metrics["s1"]["sharpe"] == 0.5
    assert set(metrics.keys()) == {"s0", "s1"}


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_param_levels_derives_all_non_split_levels() -> None:
    tuples = [("x", "s0"), ("x", "s1")]
    names = ["alpha", "split"]
    grid = CandidateGrid(_frame(tuples, names=names, columns=["v"]))
    assert grid.param_levels == ["alpha"]


def test_metric_ids_returns_column_names() -> None:
    grid = CandidateGrid(
        _filled_frame(
            [("A", "s0")],
            names=["param", "split"],
            values={"sharpe": [1.0], "total_trades": [5.0]},
        )
    )
    assert grid.metric_ids == ["sharpe", "total_trades"]


# ---------------------------------------------------------------------------
# Shape-contract tests (migrated from validity test module)
# ---------------------------------------------------------------------------


def test_empty_grid_constructs_and_iterates_empty() -> None:
    """An empty grid (no rows) constructs and yields nothing."""
    index = pd.MultiIndex.from_tuples([], names=["param", "split"])
    df = pd.DataFrame({"sharpe": []}, index=index, dtype="float64")
    grid = CandidateGrid(df)
    assert list(grid.by_candidate()) == []
    assert grid.param_levels == ["param"]
    assert grid.metric_ids == ["sharpe"]


def test_multiple_param_levels_derive_correctly() -> None:
    """Three index levels: two params + split."""
    tuples = [(5, 10, "s0"), (5, 10, "s1")]
    names = ["fast", "slow", "split"]
    grid = CandidateGrid(_frame(tuples, names=names, columns=["v"]))
    assert grid.param_levels == ["fast", "slow"]
    assert grid.metric_ids == ["v"]
