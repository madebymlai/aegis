from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt


def test_parameterized_multi_metric_output_preserves_param_index() -> None:
    @vbt.parameterized(merge_func="concat")
    def metric_pair(fast: int, slow: int) -> pd.Series:
        return pd.Series(
            {
                "total_return": float(slow - fast),
                "trade_count": float(fast + slow),
            }
        )

    result = metric_pair(vbt.Param([1, 2]), vbt.Param([3, 4]))

    assert result.index.names == ["fast", "slow", None]
    assert result.loc[(1, 3, "total_return")] == 2.0
    assert result.loc[(2, 4, "trade_count")] == 6.0


def test_parameterized_level_and_condition_define_native_candidate_rows() -> None:
    @vbt.parameterized(merge_func="concat")
    def threshold_score(entry_threshold: int, exit_threshold: int) -> float:
        return float(exit_threshold - entry_threshold)

    tied = threshold_score(
        entry_threshold=vbt.Param([40, 45], level=0),
        exit_threshold=vbt.Param([60, 55], level=0),
    )

    assert tied.index.names == ["entry_threshold", "exit_threshold"]
    assert list(tied.index) == [(40, 60), (45, 55)]

    @vbt.parameterized(merge_func="concat")
    def constrained_score(fast: int, slow: int) -> float:
        return float(slow - fast)

    constrained = constrained_score(
        fast=vbt.Param([1, 2, 3], condition="fast < slow"),
        slow=vbt.Param([2, 3]),
    )

    assert list(constrained.index) == [(1, 2), (1, 3), (2, 3)]


def test_parameterized_random_subset_exposes_actual_sampled_rows() -> None:
    @vbt.parameterized(merge_func="concat")
    def score_random(a: int, b: int, c: bool) -> float:
        return float(a + b + int(c))

    sampled = score_random(
        a=vbt.Param([1, 2, 3]),
        b=vbt.Param([10, 20]),
        c=vbt.Param([False, True]),
        _random_subset=5,
        _seed=42,
    )

    assert sampled.index.names == ["a", "b", "c"]
    assert list(sampled.index) == [
        (1, 10, False),
        (2, 10, False),
        (2, 10, True),
        (2, 20, False),
        (3, 10, True),
    ]


def test_cv_split_selects_params_from_selection_set_for_held_out_execution() -> None:
    data = _selection_negative_held_out_positive_series()

    @vbt.cv_split(
        splitter="from_n_rolling",
        splitter_kwargs={
            "n": 2,
            "length": 4,
            "split": 0.5,
            "set_labels": ["selection", "held_out"],
        },
        takeable_args=["data"],
        parameterized_kwargs={"merge_func": "concat"},
        merge_func="concat",
        selection="max",
        return_grid="all",
    )
    def split_score(data: pd.Series, leverage: float) -> float:
        return float(data.mean() * leverage)

    grid, selected = split_score(data, vbt.Param([1.0, 3.0]))

    assert grid.index.names == ["split", "set", "leverage"]
    assert selected.index.names == ["split", "set", "leverage"]
    assert list(selected.index) == [
        (0, "selection", 1.0),
        (0, "held_out", 1.0),
        (1, "selection", 1.0),
        (1, "held_out", 1.0),
    ]
    assert grid.loc[(0, "held_out", 3.0)] == 3.0
    assert selected.loc[(0, "held_out", 1.0)] == 1.0
    assert grid.loc[(1, "held_out", 3.0)] == 6.0
    assert selected.loc[(1, "held_out", 1.0)] == 2.0


def test_cv_split_return_grid_first_duplicates_selection_grid_for_each_set() -> None:
    data = _selection_negative_held_out_positive_series()

    @vbt.cv_split(
        splitter="from_n_rolling",
        splitter_kwargs={
            "n": 2,
            "length": 4,
            "split": 0.5,
            "set_labels": ["selection", "held_out"],
        },
        takeable_args=["data"],
        parameterized_kwargs={"merge_func": "concat"},
        merge_func="concat",
        selection="max",
        return_grid="first",
    )
    def split_score(data: pd.Series, leverage: float) -> float:
        return float(data.mean() * leverage)

    grid, selected = split_score(data, vbt.Param([1.0, 3.0]))

    assert grid.loc[(0, "selection", 1.0)] == -1.0
    assert grid.loc[(0, "held_out", 1.0)] == -1.0
    assert grid.loc[(1, "selection", 3.0)] == -6.0
    assert grid.loc[(1, "held_out", 3.0)] == -6.0
    assert selected.loc[(0, "held_out", 1.0)] == 1.0
    assert selected.loc[(1, "held_out", 1.0)] == 2.0


def _selection_negative_held_out_positive_series() -> pd.Series:
    return pd.Series(
        [-1.0, -1.0, 1.0, 1.0, -2.0, -2.0, 2.0, 2.0],
        index=pd.date_range("2024-01-01", periods=8, freq="D"),
    )
