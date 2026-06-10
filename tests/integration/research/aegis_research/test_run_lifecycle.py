from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.aegis_research.atomic_write import hash_file
from research.aegis_research.provenance.manifest import ArtifactStatus, RunStatus
from research.aegis_research.provenance.recorder import RerunMode, RunRecorder
from research.aegis_research.provenance.run_store import RunCollisionError, RunStore
from research.aegis_research.run_pipeline import run_strategy_sweep
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config


def test_run_recorder_starts_and_completes_manifest(tmp_path: Path) -> None:
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run-1",
        run_id="run-1",
        run_label="baseline",
        mode=RerunMode.NEW,
        config={"schema_version": 1},
    )

    assert recorder.manifest_path.exists()
    running_manifest = json.loads(recorder.manifest_path.read_text())
    assert running_manifest["run"]["status"] == RunStatus.RUNNING

    recorder.mark_run_completed()

    completed_manifest = json.loads(recorder.manifest_path.read_text())
    assert completed_manifest["run"]["status"] == RunStatus.COMPLETED
    assert completed_manifest["run"]["finished_at"]


def test_run_store_new_mode_rejects_existing_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start_run(
        run_label="baseline",
        config={"schema_version": 1},
        run_id="fixed-run",
    )

    with pytest.raises(RunCollisionError):
        store.start_run(
            run_label="baseline",
            config={"schema_version": 1},
            run_id="fixed-run",
        )


@pytest.mark.parametrize("run_id", ["../escape", "/tmp/escape", "nested/escape", "bad id"])
def test_run_store_rejects_unsafe_run_ids(tmp_path: Path, run_id: str) -> None:
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.start_run(
            run_label="baseline",
            config={"schema_version": 1},
            run_id=run_id,
        )

    assert not any(tmp_path.iterdir())


def test_run_store_rejects_relative_symlinked_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside-runs"
    outside.mkdir()
    (tmp_path / "runs").symlink_to(outside, target_is_directory=True)
    store = RunStore("runs")

    with pytest.raises(ValueError, match="symlinked"):
        store.start_run(
            run_label="baseline",
            config={"schema_version": 1},
            run_id="escape-run",
        )

    assert not (outside / "escape-run").exists()


def test_run_store_overwrite_creates_superseding_physical_run(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    original = store.start_run(
        run_label="baseline",
        config={"schema_version": 1},
        run_id="original-run",
    )
    original.mark_run_completed()

    superseding = store.start_run(
        run_label="baseline",
        config={"schema_version": 1},
        mode=RerunMode.OVERWRITE,
        run_id="new-run",
        supersedes_run_id="original-run",
    )

    assert original.manifest_path.exists()
    assert superseding.run_dir != original.run_dir
    assert superseding.manifest.lineage["supersedes_run_id"] == "original-run"


@pytest.mark.parametrize(
    ("mode", "message"),
    [(RerunMode.FORK, "parent_run_id"), (RerunMode.OVERWRITE, "supersedes_run_id")],
)
def test_run_store_requires_lineage_for_lineage_modes(
    tmp_path: Path,
    mode: str,
    message: str,
) -> None:
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match=message):
        store.start_run(
            run_label="baseline",
            config={"schema_version": 1},
            mode=mode,
            run_id="lineage-run",
        )


def test_strategy_run_initializes_manifest_before_data_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def fail_after_manifest(_config, **_kwargs):
        manifest_path = tmp_path / "runs" / "fixed-run" / "manifest.json"
        assert manifest_path.exists()
        raise RuntimeError("data stage failed")

    monkeypatch.setattr("research.aegis_research.run_pipeline.load_market_data_result", fail_after_manifest)

    with pytest.raises(RuntimeError, match="data stage failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="fixed-run",
        )

    manifest = json.loads((tmp_path / "runs" / "fixed-run" / "manifest.json").read_text())
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["stages"][0]["id"] == "run"
    assert manifest["stages"][0]["status"] == "failed"


def test_strategy_run_marks_failed_when_on_run_refs_callback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def fail_callback(_refs):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="callback-failed-run",
            on_run_refs=fail_callback,
        )

    manifest = json.loads(
        (tmp_path / "runs" / "callback-failed-run" / "manifest.json").read_text()
    )
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["stages"][0]["id"] == "run"
    assert manifest["stages"][0]["status"] == "failed"


def test_failed_run_diagnostic_is_length_clipped_not_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REMOTE_TOKEN", "super-secret-token")
    resolved = build_resolved_run_config(
        tmp_path,
        data={
            "source": "yf",
            "symbols": ["SYN"],
            "start": "2020-01-01",
            "end": "2021-01-01",
            "timeframe": "1D",
            "provider_kwargs": {"api_token": {"env": "REMOTE_TOKEN"}},
        },
    )

    long_message = "provider returned super-secret-token " + "x" * 2000

    def fail_with_secret(_config, **_kwargs):
        raise RuntimeError(long_message)

    monkeypatch.setattr("research.aegis_research.run_pipeline.load_market_data_result", fail_with_secret)

    with pytest.raises(RuntimeError, match="provider returned"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="secret-failed-run",
        )

    manifest = json.loads((tmp_path / "runs" / "secret-failed-run" / "manifest.json").read_text())
    diagnostic = manifest["stages"][0]["diagnostic"]
    assert diagnostic["message"] == long_message[:1000]
    assert "<redacted>" not in diagnostic["message"]
    assert diagnostic["message"].startswith("provider returned super-secret-token")


def test_artifact_registry_persists_planned_and_writing_transitions(tmp_path: Path) -> None:
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run-1",
        run_id="run-1",
        run_label="baseline",
        mode=RerunMode.NEW,
        config={"schema_version": 1},
    )

    recorder.artifacts.plan_artifact(
        artifact_id="report.survival",
        role="survival_report",
        artifact_type="json",
        producer_stage="report",
        path="survival_report.json",
        schema_version="survival_report.v1",
    )
    planned = json.loads(recorder.manifest_path.read_text())
    assert planned["artifacts"][0]["status"] == "planned"

    recorder.artifacts.begin_artifact_write("report.survival")
    writing = json.loads(recorder.manifest_path.read_text())
    assert writing["artifacts"][0]["status"] == "writing"

    artifact_path = recorder.run_dir / "survival_report.json"
    artifact_path.write_text("{}\n")
    recorder.artifacts.complete_existing_file("report.survival")
    completed = json.loads(recorder.manifest_path.read_text())
    artifact = completed["artifacts"][0]
    assert artifact["status"] == ArtifactStatus.COMPLETED
    assert artifact["hash"] == hash_file(artifact_path)
    assert artifact["size"] == artifact_path.stat().st_size
