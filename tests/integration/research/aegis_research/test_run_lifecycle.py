from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from research.aegis_research.config import (
    DataConfig,
    ExperimentConfig,
    ModelConfig,
    load_experiment_config,
    resolve_experiment_config,
)
from research.aegis_research.experiments import run_experiment
from research.aegis_research.provenance.manifest import ArtifactStatus, RunStatus, hash_file
from research.aegis_research.provenance.recorder import RerunMode, RunRecorder
from research.aegis_research.provenance.run_store import RunCollisionError, RunStore
from tests.support.research.aegis_research.experiment_config_fixtures import (
    SYNTHETIC_ML_SCAFFOLD_CONFIG,
)
from tests.support.research.aegis_research.model_plugin_fixtures import (
    make_model_registry,
    model_config_dict,
)


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


def test_run_experiment_initializes_manifest_before_data_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = make_model_registry()
    resolved = load_experiment_config(SYNTHETIC_ML_SCAFFOLD_CONFIG, model_registry=registry)
    resolved = resolve_experiment_config(
        replace(resolved.config, output_dir=str(tmp_path)), model_registry=registry
    )

    def fail_after_manifest(_config, **_kwargs):
        manifest_path = tmp_path / "fixed-run" / "manifest.json"
        assert manifest_path.exists()
        raise RuntimeError("data stage failed")

    monkeypatch.setattr(
        "research.aegis_research.experiments.load_market_data_result", fail_after_manifest
    )

    with pytest.raises(RuntimeError, match="data stage failed"):
        run_experiment(resolved, run_id="fixed-run")

    manifest = json.loads((tmp_path / "fixed-run" / "manifest.json").read_text())
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["stages"][0]["id"] == "run"
    assert manifest["stages"][0]["status"] == "failed"


def test_run_experiment_marks_failed_when_run_started_callback_fails(tmp_path: Path) -> None:
    registry = make_model_registry()
    resolved = load_experiment_config(SYNTHETIC_ML_SCAFFOLD_CONFIG, model_registry=registry)
    resolved = resolve_experiment_config(
        replace(resolved.config, output_dir=str(tmp_path)), model_registry=registry
    )

    def fail_callback(_refs):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        run_experiment(resolved, run_id="callback-failed-run", on_run_started=fail_callback)

    manifest = json.loads((tmp_path / "callback-failed-run" / "manifest.json").read_text())
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["stages"][0]["id"] == "run"
    assert manifest["stages"][0]["status"] == "failed"


def test_failed_run_diagnostic_redacts_config_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REMOTE_TOKEN", "super-secret-token")
    resolved = resolve_experiment_config(
        ExperimentConfig(
            name="secret-diagnostic",
            output_dir=str(tmp_path),
            model=ModelConfig(**model_config_dict(min_train_samples=50)),
            data=DataConfig(
                source="yf",
                symbols=["SYN"],
                start="2020-01-01",
                end="2021-01-01",
                timeframe="1D",
                provider_kwargs={"api_token": {"env": "REMOTE_TOKEN"}},
            ),
        ),
        model_registry=make_model_registry(),
    )

    def fail_with_secret(_config, **_kwargs):
        raise RuntimeError("provider returned super-secret-token")

    monkeypatch.setattr(
        "research.aegis_research.experiments.load_market_data_result", fail_with_secret
    )

    with pytest.raises(RuntimeError, match="provider returned"):
        run_experiment(resolved, run_id="secret-failed-run")

    manifest = json.loads((tmp_path / "secret-failed-run" / "manifest.json").read_text())
    diagnostic = manifest["stages"][0]["diagnostic"]
    assert diagnostic["message"] == "provider returned <redacted>"
    assert "super-secret-token" not in json.dumps(manifest)


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
