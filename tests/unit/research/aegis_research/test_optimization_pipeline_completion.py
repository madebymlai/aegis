"""Unit tests for pipeline completion stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.pipeline.completion import run_pipeline_completion
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


def test_pipeline_completion_returns_expected_keys(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """run_pipeline_completion returns the final result dict with run refs and metadata."""
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config

    class _FakeRun:
        ranking_metric = "total_return"
        ranking_direction = "desc"
        selection = __import__("pandas").Index([0])

    class _FakeSplitResult:
        metadata = {"n_splits": 2}
        splits = []

    class _FakeRecorder:
        run_dir = tmp_path / "runs" / "test-run"
        manifest_path = tmp_path / "runs" / "test-run" / "manifest.json"

        class manifest:
            run_id = "test-run-id"
            status = "completed"
            started_at = "2024-01-01T00:00:00Z"
            finished_at = "2024-01-01T00:01:00Z"

        class artifacts:
            @staticmethod
            def begin_artifact_write(artifact_id: str) -> None:
                pass

            @staticmethod
            def complete_artifact(
                artifact_id: str, *, content_hash: str, size: int, shape: dict[str, int]
            ) -> None:
                pass

            @staticmethod
            def plan_artifact(
                artifact_id: str,
                role: str,
                artifact_type: str,
                producer_stage: str,
                path: str,
                schema_version: str,
            ) -> None:
                pass

        def mark_run_completed(self) -> None:
            pass

    class _FakeDataResult:
        class quality:
            state = "ok"

        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
            "effective_arrays": ["OHLCV"],
        }

    class _FakeArrayContract:
        def metadata(self) -> dict[str, Any]:
            return {"required": ["Close", "Open"]}

    store_path = tmp_path / ".candidate_store" / "candidates.sqlite3"
    store_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "research.aegis_research.optimization.pipeline.completion.activate_candidate_run",
        lambda store_path, run_id: None,
    )

    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)

    result = run_pipeline_completion(
        config=config,
        recorder=_FakeRecorder(),
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        strategy_evidence={"family": "strategies", "id": "demo.strategy"},
        optimization_builtin={"search": "grid"},
        portfolio_builtin={"target_exposure_cap": 1.0},
        split_result=_FakeSplitResult(),
        optimization_evidence={
            "schema_version": "optimization_route.v1",
            "preflight": {"computed_mono_chunk_len": 1},
            "execution": {"sampled_rows": {"rows": []}},
        },
        run_payload={"sampled_rows": {"rows": []}},
        candidate_rows=[],
        leaderboard={"rows": [], "summary": {}},
        resolved_locks=[],
        lock_records=[],
        candidate_store_provenance={"schema_version": "candidate_store_provenance.v1"},
        store_path=store_path,
        store_namespace={"kind": "local_sqlite", "path": ".candidate_store/candidates.sqlite3"},
        optimization_run=_FakeRun(),
        metric_registry_fingerprint=None,
    )

    expected_keys = {
        "run_id",
        "run_dir",
        "manifest_path",
        "status",
        "started_at",
        "finished_at",
        "strategy_artifact_id",
        "strategy_artifact_path",
        "candidate_store_path",
        "locks",
        "optimization",
        "leaderboard",
    }
    assert set(result.keys()) == expected_keys
    assert result["strategy_artifact_id"] == "strategy.run"
    assert result["optimization"]["split_count"] == 2
    assert result["optimization"]["selection_row_count"] == 1
    assert result["optimization"]["candidate_count"] == 0
