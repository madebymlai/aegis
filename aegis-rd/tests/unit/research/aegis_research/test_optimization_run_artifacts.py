from __future__ import annotations

from typing import Any, ClassVar

from research.aegis_research.optimization.run_artifacts import (
    OPTIMIZATION_ARTIFACT_SCHEMA_VERSION,
    find_strategy_artifact_record,
    strategy_artifact_shape,
)


def test_optimization_artifact_schema_version_is_stable() -> None:
    assert OPTIMIZATION_ARTIFACT_SCHEMA_VERSION == "optimization_artifact.v2"


def test_strategy_artifact_shape_counts_candidates_and_observation_blocks() -> None:
    """Shape reflects candidate and Observation Block counts."""
    payload: dict[str, Any] = {
        "candidates": [{"role": "best"}, {"role": "median"}, {"role": "worst"}],
        "selection": {
            "observation_block_bounds": [[0, 20], [20, 40], [40, 60], [60, 80]]
        },
    }

    shape = strategy_artifact_shape(payload)

    assert shape["candidate_count"] == 3
    assert shape["observation_block_count"] == 4
    assert "leaderboard_rows" not in shape


def test_strategy_artifact_shape_missing_selection() -> None:
    """Shape records zero Observation Blocks when selection metadata is absent."""
    payload: dict[str, Any] = {
        "candidates": [],
    }

    shape = strategy_artifact_shape(payload)

    assert shape["candidate_count"] == 0
    assert shape["observation_block_count"] == 0


def test_find_strategy_artifact_record_finds_matching_artifact() -> None:
    """find_strategy_artifact_record returns the record with id 'strategy.run'."""

    class _FakeRecorder:
        class manifest:
            artifacts: ClassVar = [
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
            artifacts: ClassVar = [
                {"id": "data.metadata"},
                {"id": "other"},
            ]

    record = find_strategy_artifact_record(_FakeRecorder())
    assert record is None
