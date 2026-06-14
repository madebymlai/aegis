"""Unit tests for the pipeline completion stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_PENDING,
    CandidateStore,
)
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.completion import (
    run_pipeline_completion,
)
from research.aegis_research.optimization.pipeline.publishing import PublishingResult
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_run_config,
    make_setup_result,
)
from tests.support.research.aegis_research.test_doubles import (
    FakeArrayContract,
    FakeDataResult,
    FakeRecorder,
)


def _candidate_rows() -> list[dict[str, Any]]:
    """Build three role-tagged candidate rows matching the publishing-stage output."""
    return [
        {
            "role": "best",
            "rank": 1,
            "candidate_key": "fast=5:slow=10",
            "params": {"fast": 5, "slow": 10},
            "score": 0.30,
            "metrics": {"total_return": 0.30},
            "selection_metrics": {0: {"total_return": 0.30}},
            "held_out_metrics": {0: {"total_return": 0.29}},
            "held_out_metrics_mean": {"total_return": 0.29},
            "identity": {"params": {"fast": 5, "slow": 10}},
        },
        {
            "role": "median",
            "rank": 2,
            "candidate_key": "fast=2:slow=10",
            "params": {"fast": 2, "slow": 10},
            "score": 0.20,
            "metrics": {"total_return": 0.20},
            "selection_metrics": {0: {"total_return": 0.20}},
            "held_out_metrics": {0: {"total_return": 0.19}},
            "held_out_metrics_mean": {"total_return": 0.19},
            "identity": {"params": {"fast": 2, "slow": 10}},
        },
        {
            "role": "worst",
            "rank": 3,
            "candidate_key": "fast=8:slow=20",
            "params": {"fast": 8, "slow": 20},
            "score": 0.10,
            "metrics": {"total_return": 0.10},
            "selection_metrics": {0: {"total_return": 0.10}},
            "held_out_metrics": {0: {"total_return": 0.09}},
            "held_out_metrics_mean": {"total_return": 0.09},
            "identity": {"params": {"fast": 8, "slow": 20}},
        },
    ]


def test_completion_returns_result_and_marks_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completion stage returns CLI-facing result dict, marks run completed,
    and activates the candidate run in the store."""
    config = make_run_config(optimization=make_optimization_config())
    store_path = tmp_path / "candidates.sqlite3"
    setup = make_setup_result(store_path=store_path)
    run_id = "run-cmp"
    run_dir = tmp_path / "runs" / run_id

    candidate_rows = _candidate_rows()
    publishing = PublishingResult(
        candidate_rows=tuple(candidate_rows),
        candidate_store_provenance={"schema_version": "candidate_store_provenance.v1"},
    )

    # Pre-populate the candidate store in pending state (mimics publishing output).
    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id=run_id,
            candidate_rows=candidate_rows,
            provenance=publishing.candidate_store_provenance,
            publication_state=PUBLICATION_PENDING,
        )

    recorder = FakeRecorder(run_id, run_dir)
    run_evidence = RunEvidence(
        recorder.manifest.evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={
            "schema_version": OPTIMIZATION_ROUTE_SCHEMA_VERSION,
            "preflight": {},
            "execution": {
                "total": 30,
                "excluded_invalid": 2,
                "excluded_degenerate": 3,
            },
        },
        persist=lambda: None,
    )

    # Mock write_strategy_artifact to avoid filesystem side-effects while
    # capturing the payload that would have been written.
    captured_artifact: dict[str, Any] = {}

    def _capture_write(_rec: object, payload: dict[str, Any]) -> None:
        captured_artifact.update(payload)

    monkeypatch.setattr(
        "research.aegis_research.optimization.pipeline.completion.write_strategy_artifact",
        _capture_write,
    )

    result = run_pipeline_completion(
        setup=setup,
        publishing=publishing,
        config=config,
        recorder=recorder,
        data_result=FakeDataResult(),
        array_contract=FakeArrayContract(),
        run_evidence=run_evidence,
        metric_registry_fingerprint="test-fp",
    )

    # Assert returned result dict
    assert result["run_id"] == run_id
    assert result["run_dir"] == str(run_dir)
    assert result["manifest_path"] == str(run_dir / "manifest.json")
    assert result["strategy_artifact_id"] == "strategy.run"
    assert result["strategy_artifact_path"] == str(run_dir / "strategy_run.json")
    assert result["candidate_store_path"] == str(store_path)
    assert result["status"] == "completed"
    assert result["started_at"] == "2025-01-01T00:00:00Z"
    assert result["finished_at"] == "2025-01-01T01:00:00Z"

    opt = result["optimization"]
    assert opt["ranking_metric"] == "total_return"
    assert opt["min_weight"] == 0.3
    assert opt["split_count"] == 2
    assert opt["candidate_count"] == 3
    assert opt["total"] == 30
    assert opt["excluded_invalid"] == 2
    assert opt["excluded_degenerate"] == 3
    # held-out gap 0.01 < threshold 0.10, so no warning
    assert opt["held_out_warning"] is None
    # non_executable_rows defaults to 0 when absent from execution evidence
    assert opt["non_executable_rows"] == 0
    # split method flows from config into the report's optimization summary
    assert opt["split_method"] == config.optimization.split.method

    candidates = result["candidates"]
    assert [c["role"] for c in candidates] == ["best", "median", "worst"]
    assert [c["rank"] for c in candidates] == [1, 2, 3]
    assert candidates[0]["score"] == pytest.approx(0.30)
    assert candidates[1]["score"] == pytest.approx(0.20)
    assert candidates[2]["score"] == pytest.approx(0.10)

    best = candidates[0]
    assert best["held_out_headline"]["metric"] == "total_return"
    assert best["held_out_headline"]["selection"] == pytest.approx(0.30)
    assert best["held_out_headline"]["held_out"] == pytest.approx(0.29)
    assert best["held_out_headline"]["gap"] == pytest.approx(0.01)

    # aegis-rd-gg3.2: lock handles are payload data
    assert candidates[0]["lock"] == run_id  # best = bare run_id
    assert candidates[1]["lock"] == f"{run_id}:median"
    assert candidates[2]["lock"] == f"{run_id}:worst"

    # Assert completion marking
    assert recorder.manifest.status == "completed"
    assert recorder.manifest.finished_at == "2025-01-01T01:00:00Z"

    # Assert candidate-run activation
    # candidate_key_for_role resolves PUBLICATION_ACTIVE rows only.
    with CandidateStore(store_path) as store:
        stored = [
            store.candidate_by_key(
                store.candidate_key_for_role(run_id, role), run_id=run_id
            )
            for role in ("best", "median", "worst")
        ]
    scores = [row["candidate"]["score"] for row in stored]
    assert scores == pytest.approx([0.30, 0.20, 0.10])

    # Assert artifact payload structure
    assert "schema_version" in captured_artifact
    assert "strategy" in captured_artifact
    assert len(captured_artifact["candidates"]) == 3
    assert captured_artifact["candidate_store"]["path"] == ".candidate_store/candidates.sqlite3"
    assert captured_artifact["metric_registry_fingerprint"] == "test-fp"
