"""Unit tests for the pipeline completion stage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.optimization.candidate_evidence import (
    candidate_rows_from_result,
)
from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_PENDING,
    CandidateStore,
)
from research.aegis_research.optimization.candidate_store_identity import (
    CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
)
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.completion import (
    run_pipeline_completion,
)
from research.aegis_research.optimization.pipeline.publishing import PublishingResult
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_run_config,
    make_run_data_facts,
    make_selection_identity,
    make_setup_result,
)
from tests.support.research.aegis_research.test_doubles import (
    FakeArrayContract,
    FakeDataResult,
    FakeRecorder,
)


def _candidate_rows() -> list[dict[str, Any]]:
    """Build three role-tagged candidate rows matching the publishing-stage output."""

    def candidate(fast: int, slow: int, score: float) -> EvaluatedCandidate:
        return EvaluatedCandidate(
            params={"fast": fast, "slow": slow},
            score=score,
            observation_block_metrics={"block-000": {"total_return": score}},
            metrics={"total_return": score},
        )

    result = OptimizationResult(
        best=candidate(5, 10, 0.30),
        median=candidate(2, 10, 0.20),
        worst=candidate(8, 20, 0.10),
    )
    return candidate_rows_from_result(
        result,
        source_identity={},
        data_identity={},
        selection_identity=make_selection_identity(),
    )


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
        candidate_store_provenance={
            "schema_version": CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
            "selection_identity": make_selection_identity(),
        },
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
            "preflight": {
                "observation_block_bars": 20,
                "observation_block_count": 2,
                "observation_block_bounds": [[0, 20], [20, 40]],
            },
            "execution": {
                "candidate_accounting": {
                    "total": 30,
                    "excluded_invalid": 2,
                    "excluded_degenerate": 3,
                },
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
        facts=make_run_data_facts(
            data_result=FakeDataResult(),
            array_contract=FakeArrayContract(),
            metric_registry_fingerprint="test-fp",
        ),
        run_evidence=run_evidence,
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
    assert opt["protocol"] == "continuous_future_in_past"
    assert opt["observation_block_bars"] == 20
    assert opt["observation_block_count"] == 2
    assert opt["candidate_count"] == 3
    assert opt["total"] == 30
    assert opt["excluded_invalid"] == 2
    assert opt["excluded_degenerate"] == 3
    assert "held_out_warning" not in opt
    assert "separability_warning" not in opt
    assert "split_method" not in opt

    candidates = result["candidates"]
    assert [c["role"] for c in candidates] == ["best", "median", "worst"]
    assert [c["ordinal_rank"] for c in candidates] == [1, 2, 3]
    assert candidates[0]["mean_rank"] == pytest.approx(0.30)
    assert candidates[1]["mean_rank"] == pytest.approx(0.20)
    assert candidates[2]["mean_rank"] == pytest.approx(0.10)

    assert "held_out_headline" not in candidates[0]

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
            store.candidate_by_key(store.candidate_key_for_role(run_id, role), run_id=run_id)
            for role in ("best", "median", "worst")
        ]
    scores = [row["candidate"]["mean_rank"] for row in stored]
    assert scores == pytest.approx([0.30, 0.20, 0.10])

    # Assert artifact payload structure
    assert "schema_version" in captured_artifact
    assert "strategy" in captured_artifact
    assert len(captured_artifact["candidates"]) == 3
    assert captured_artifact["candidate_store"]["path"] == ".candidate_store/candidates.sqlite3"
    assert captured_artifact["metric_registry_fingerprint"] == "test-fp"
