"""Tests at the run-output entry seam (aegis-rd-gg3.3, ADR-0021).

``build_run_payload`` is the single public entry that owns the run success
payload shape: it projects the selection block from the typed config-selection
evidence, the run block via the shared ``run_refs`` projection, and passes the
optimization/candidates blocks through with real resolved paths.
"""

from __future__ import annotations

from research.aegis_research.cli_support.run_output import build_run_payload
from research.aegis_research.configuration import ConfigSelectionEvidence


def _sweep_result() -> dict[str, object]:
    return {
        "run_id": "run-abc",
        "status": "completed",
        "run_dir": "/data/runs/run-abc",
        "manifest_path": "/data/runs/run-abc/manifest.json",
        "started_at": "2026-06-12T00:00:00Z",
        "finished_at": "2026-06-12T00:01:00Z",
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": "/data/runs/run-abc/strategy_run.json",
        "candidate_store_path": "/data/runs/.candidate_store/candidates.sqlite3",
        "optimization": {"total": 4, "held_out_warning": None},
        "candidates": [{"role": "best", "lock": "run-abc"}],
    }


def _evidence() -> ConfigSelectionEvidence:
    return ConfigSelectionEvidence(source="explicit", config_path="/data/cfg.yaml")


def test_selection_block_is_projected_from_typed_evidence() -> None:
    payload = build_run_payload(_sweep_result(), selection_evidence=_evidence())

    assert payload["selection"] == {"source": "explicit", "config_path": "/data/cfg.yaml"}


def test_run_block_is_the_shared_run_refs_projection_with_real_paths() -> None:
    payload = build_run_payload(_sweep_result(), selection_evidence=_evidence())

    assert payload["run"] == {
        "id": "run-abc",
        "status": "completed",
        "run_dir": "/data/runs/run-abc",
        "manifest_path": "/data/runs/run-abc/manifest.json",
        "started_at": "2026-06-12T00:00:00Z",
        "finished_at": "2026-06-12T00:01:00Z",
    }


def test_artifact_and_candidate_store_paths_are_real_absolute_paths() -> None:
    payload = build_run_payload(_sweep_result(), selection_evidence=_evidence())

    assert payload["artifacts"] == {
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": "/data/runs/run-abc/strategy_run.json",
    }
    assert payload["candidate_store"] == {
        "path": "/data/runs/.candidate_store/candidates.sqlite3"
    }


def test_optimization_and_candidates_blocks_pass_through() -> None:
    payload = build_run_payload(_sweep_result(), selection_evidence=_evidence())

    assert payload["optimization"] == {"total": 4, "held_out_warning": None}
    assert payload["candidates"] == [{"role": "best", "lock": "run-abc"}]


def test_missing_optional_result_keys_project_to_empty_blocks() -> None:
    payload = build_run_payload(
        {"run_id": "run-abc", "status": "completed"},
        selection_evidence=_evidence(),
    )

    assert payload["run"]["run_dir"] is None
    assert payload["artifacts"]["strategy_artifact_path"] is None
    assert payload["candidate_store"]["path"] is None
    assert payload["optimization"] == {}
    assert payload["candidates"] == []
