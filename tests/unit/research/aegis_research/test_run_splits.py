from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.config import RunSplitConfig
from research.aegis_research.run_splits import build_run_splits_result


def test_build_run_splits_result_invokes_from_rolling_with_public_evidence() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    result = build_run_splits_result(
        index,
        RunSplitConfig(
            method="from_rolling",
            params={"length": 6, "split": 0.5},
        ),
    )

    assert result.metadata["method"] == "from_rolling"
    assert result.metadata["params"]["length"] == 6
    assert result.metadata["set_usage_policy"] == "exactly_two_sets_first_selection_second_held_out"
    assert result.metadata["n_splits"] > 0
    assert result.splits[0].selection_set == "set_0"
    assert result.splits[0].held_out_set == "set_1"
    assert result.splits[0].selection_index.intersection(result.splits[0].held_out_index).empty
    first_split = result.metadata["splits"][0]
    assert "membership" in first_split["sets"]["selection"]
    assert "membership" in first_split["sets"]["held_out"]
    assert result.metadata["sets"] == [
        {"role": "selection", "position": 0},
        {"role": "held_out", "position": 1},
    ]


def test_build_run_splits_result_invokes_purged_kfold_generically() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    result = build_run_splits_result(
        index,
        RunSplitConfig(method="from_purged_kfold", params={"n_folds": 3, "n_test_folds": 1}),
    )

    assert result.metadata["method"] == "from_purged_kfold"
    assert result.metadata["n_splits"] == 3
    assert result.splits[0].selection_set == "train"
    assert result.splits[0].held_out_set == "test"
    assert result.metadata["sets"] == [
        {"role": "selection", "position": 0},
        {"role": "held_out", "position": 1},
    ]


def test_build_run_splits_result_preserves_single_split_two_set_output() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    result = build_run_splits_result(
        index,
        RunSplitConfig(
            method="from_rolling",
            params={"length": 12, "split": 0.5},
        ),
    )

    assert result.metadata["n_splits"] == 1
    assert result.splits[0].selection_set == "set_0"
    assert result.splits[0].held_out_set == "set_1"


def test_build_run_splits_result_rejects_one_set_output() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    with pytest.raises(ValueError, match="exactly two sets"):
        build_run_splits_result(index, RunSplitConfig(method="from_rolling", params={"length": 4}))


def test_build_run_splits_result_rejects_three_set_output() -> None:
    index = pd.date_range("2024-01-01", periods=30, freq="D")

    with pytest.raises(ValueError, match="exactly two sets"):
        build_run_splits_result(
            index,
            RunSplitConfig(
                method="from_rolling",
                params={
                    "length": 20,
                    "split": [0.6, 0.2, 0.2],
                },
            ),
        )


def test_build_run_splits_result_enforces_split_count_guard() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    with pytest.raises(ValueError, match="max_splits"):
        build_run_splits_result(
            index,
            RunSplitConfig(
                method="from_rolling",
                params={"length": 4, "split": 0.5},
                max_splits=1,
            ),
        )


def test_build_run_splits_result_enforces_estimated_output_cell_guard() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    with pytest.raises(ValueError, match="max_estimated_output_cells"):
        build_run_splits_result(
            index,
            RunSplitConfig(
                method="from_rolling",
                params={"length": 6, "split": 0.5},
                max_estimated_output_cells=1,
            ),
        )


def test_build_run_splits_result_enforces_public_artifact_guard() -> None:
    index = pd.date_range("2024-01-01", periods=12, freq="D")

    with pytest.raises(ValueError, match="max_public_artifact_bytes"):
        build_run_splits_result(
            index,
            RunSplitConfig(
                method="from_rolling",
                params={"length": 6, "split": 0.5},
                max_public_artifact_bytes=1,
            ),
        )
