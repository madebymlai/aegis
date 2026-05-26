from __future__ import annotations

from typing import Any

import pytest

from research.aegis_research.optimization.run_artifacts import (
    OPTIMIZATION_ARTIFACT_SCHEMA_VERSION,
    build_strategy_artifact_payload,
    find_strategy_artifact_record,
    strategy_artifact_shape,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_optimization_artifact_schema_version_is_stable() -> None:
    assert OPTIMIZATION_ARTIFACT_SCHEMA_VERSION == "optimization_artifact.v1"


def test_build_strategy_artifact_payload_structure(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """The artifact payload includes all required top-level keys."""
    resolved = build_resolved_run_config(tmp_path)

    payload = build_strategy_artifact_payload(
        strategy_evidence={"family": "strategies", "id": "demo.strategy"},
        data_result=_fake_data_result(),
        array_contract=resolved.component_registry,
        ranking={"metric": "total_return", "direction": "desc"},
        portfolio={"target_exposure_cap": 1.0},
        optimization={"search": "grid"},
        split_metadata={"n_splits": 2},
        preflight={"computed_mono_chunk_len": 1},
        execution={"sampled_rows": {"rows": []}},
        candidates=[],
        leaderboard={"rows": []},
        resolved_locks=[],
        lock_records=[],
        candidate_store_path=".candidate_store/candidates.sqlite3",
        candidate_store_provenance={"schema_version": "candidate_store_provenance.v1"},
        metric_registry_fingerprint=None,
    )

    assert payload["schema_version"] == OPTIMIZATION_ARTIFACT_SCHEMA_VERSION
    assert payload["strategy"]["family"] == "strategies"
    assert payload["data"]["strategy_consumed_runner_data"] is True
    assert payload["ranking"]["metric"] == "total_return"
    assert payload["portfolio"]["target_exposure_cap"] == 1.0
    assert payload["optimization"]["search"] == "grid"
    assert payload["split"]["n_splits"] == 2
    assert payload["preflight"]["computed_mono_chunk_len"] == 1
    assert payload["execution"]["sampled_rows"]["rows"] == []
    assert payload["candidates"] == []
    assert payload["leaderboard"]["rows"] == []
    assert payload["resolved_locks"] == []
    assert payload["locks"] == []
    assert payload["candidate_store"]["path"] == ".candidate_store/candidates.sqlite3"
    assert payload["candidate_store"]["schema_version"] == "candidate_store_ref.v1"
    assert payload["metric_registry_fingerprint"] is None


def test_build_strategy_artifact_payload_includes_candidates_and_locks(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Candidates and locks are included as lists in the payload."""
    resolved = build_resolved_run_config(tmp_path)

    payload = build_strategy_artifact_payload(
        strategy_evidence={"family": "strategies", "id": "demo.strategy"},
        data_result=_fake_data_result(),
        array_contract=resolved.component_registry,
        ranking={"metric": "total_return", "direction": "desc"},
        portfolio={"target_exposure_cap": 1.0},
        optimization={"search": "grid"},
        split_metadata={"n_splits": 2},
        preflight={"computed_mono_chunk_len": 1},
        execution={"sampled_rows": {"rows": []}},
        candidates=[
            {"candidate_key": "abc", "params": {"fast_window": 2}},
            {"candidate_key": "def", "params": {"fast_window": 3}},
        ],
        leaderboard={"rows": [{"candidate_key": "abc", "rank": 1}]},
        resolved_locks=[],
        lock_records=[
            {"token": "lock_abc", "component_family": "strategies", "rank": 1},
        ],
        candidate_store_path=".candidate_store/candidates.sqlite3",
        candidate_store_provenance={"schema_version": "candidate_store_provenance.v1"},
        metric_registry_fingerprint="abc123",
    )

    assert len(payload["candidates"]) == 2
    assert payload["candidates"][0]["candidate_key"] == "abc"
    assert len(payload["locks"]) == 1
    assert payload["locks"][0]["token"] == "lock_abc"
    assert payload["leaderboard"]["rows"][0]["rank"] == 1
    assert payload["metric_registry_fingerprint"] == "abc123"


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


def _fake_data_result() -> object:
    class _Fake:
        class quality:
            state = "ok"

        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
        }

    return _Fake()
