from __future__ import annotations

from typing import Any

from research.aegis_research.optimization.run_artifacts import (
    OPTIMIZATION_ARTIFACT_SCHEMA_VERSION,
    find_strategy_artifact_record,
    strategy_artifact_shape,
)


def test_optimization_artifact_schema_version_is_stable() -> None:
    assert OPTIMIZATION_ARTIFACT_SCHEMA_VERSION == "optimization_artifact.v1"


def test_strategy_artifact_shape_counts_rows_and_splits() -> None:
    """Shape reflects leaderboard rows, candidate count, and split count."""
    payload: dict[str, Any] = {
        "leaderboard": {"rows": [{"rank": 1}, {"rank": 2}, {"rank": 3}]},
        "candidates": [{"a": 1}, {"a": 2}],
        "split": {"n_splits": 4},
    }

    shape = strategy_artifact_shape(payload)

    assert shape["leaderboard_rows"] == 3
    assert shape["candidate_count"] == 2
    assert shape["split_count"] == 4


def test_strategy_artifact_shape_missing_split() -> None:
    """Shape omits split_count when split key is absent."""
    payload: dict[str, Any] = {
        "leaderboard": {"rows": []},
    }

    shape = strategy_artifact_shape(payload)

    assert shape["leaderboard_rows"] == 0
    assert shape["candidate_count"] == 0
    assert "split_count" not in shape


def test_find_strategy_artifact_record_finds_matching_artifact() -> None:
    """find_strategy_artifact_record returns the record with id 'strategy.run'."""

    class _FakeRecorder:
        class manifest:
            artifacts = [
                {"id": "data.metadata"},
                {"id": "strategy.run", "role": "optimization_evidence"},
                {"id": "other"},
            ]

    record = find_strategy_artifact_record(_FakeRecorder())
    assert record is not None
    assert record["id"] == "strategy.run"
    assert record["role"] == "optimization_evidence"


def test_find_strategy_artifact_record_returns_none_when_absent() -> None:
    """find_strategy_artifact_record returns None when no strategy.run record exists."""

    class _FakeRecorder:
        class manifest:
            artifacts = [
                {"id": "data.metadata"},
                {"id": "other"},
            ]

    record = find_strategy_artifact_record(_FakeRecorder())
    assert record is None
