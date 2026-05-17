from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from research.aegis_research import data, indicators, labels, models, portfolios, signals, splits
from research.aegis_research import validation as validation_module
from research.aegis_research.config import load_experiment_config, resolve_experiment_config
from research.aegis_research.experiments import run_experiment
from research.aegis_research.provenance import artifacts, manifest
from research.aegis_research.provenance.manifest import ArtifactStatus, RunStatus, validate_manifest


def test_run_experiment_writes_manifest_backed_artifacts(tmp_path: Path) -> None:
    config = load_experiment_config("research/configs/experiments/synthetic_ml_baseline.yaml")
    config = resolve_experiment_config(replace(config.config, output_dir=str(tmp_path)))

    result = run_experiment(config, run_id="holdout-run")

    run_dir = Path(result["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(manifest, run_dir=run_dir)

    assert result["status"] == RunStatus.COMPLETED
    assert result["report_artifact_id"] == "report.survival"
    assert manifest["run"]["status"] == RunStatus.COMPLETED
    artifact_ids = {artifact["id"] for artifact in manifest["artifacts"]}
    assert "config.resolved" in artifact_ids
    assert "config.authored" in artifact_ids
    assert "data.metadata" in artifact_ids
    assert "data.native" in artifact_ids
    assert "indicators.metadata" in artifact_ids
    assert "indicators.lineage" in artifact_ids
    assert "indicators.diagnostics" in artifact_ids
    assert "indicators.features.schema" in artifact_ids
    assert "indicators.native" in artifact_ids
    assert "indicators.native.metadata" in artifact_ids
    assert "report.survival" in artifact_ids
    config_manifest = next(artifact for artifact in manifest["artifacts"] if artifact["id"] == "config.manifest")
    assert config_manifest["visibility"] == "private"
    assert "validation.holdout.model" in artifact_ids
    assert "validation.holdout.portfolio.test" in artifact_ids
    feature_schema = json.loads((run_dir / "indicators" / "features.schema.json").read_text())
    assert feature_schema["features"]
    assert feature_schema["features"][0]["name"]
    assert "native_objects" not in json.dumps(feature_schema)
    assert all(artifact["status"] == ArtifactStatus.COMPLETED for artifact in manifest["artifacts"])
    assert not (run_dir / "artifacts" / "model.joblib").exists()


def test_walkforward_run_writes_per_split_models_and_links_aggregates(tmp_path: Path) -> None:
    config = load_experiment_config(
        "research/configs/experiments/synthetic_walkforward_baseline.yaml"
    )
    config = resolve_experiment_config(replace(config.config, output_dir=str(tmp_path)))

    result = run_experiment(config, run_id="rolling-run")

    run_dir = Path(result["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(manifest, run_dir=run_dir)
    artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
    model_ids = [artifact_id for artifact_id in artifacts if artifact_id.endswith(".model")]

    assert len(model_ids) == 5
    assert "model" not in artifacts
    assert artifacts["validation.probabilities"]["upstream_artifact_ids"]
    assert artifacts["report.survival"]["upstream_artifact_ids"] == ["validation.split_metrics"]


def test_failed_walkforward_run_preserves_prior_completed_split_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_experiment_config(
        "research/configs/experiments/synthetic_walkforward_baseline.yaml"
    )
    config = resolve_experiment_config(replace(config.config, output_dir=str(tmp_path)))
    original_train_model = validation_module.train_model
    call_count = 0

    def fail_on_third_split(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("split 3 failed")
        return original_train_model(*args, **kwargs)

    monkeypatch.setattr(validation_module, "train_model", fail_on_third_split)

    with pytest.raises(RuntimeError, match="split 3 failed"):
        run_experiment(config, run_id="rolling-failed-run")

    run_dir = tmp_path / "rolling-failed-run"
    payload = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(payload, run_dir=run_dir)
    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}

    assert payload["run"]["status"] == RunStatus.FAILED
    assert artifacts["validation.split_0.model"]["status"] == ArtifactStatus.COMPLETED
    assert artifacts["validation.split_1.model"]["status"] == ArtifactStatus.COMPLETED
    assert "validation.split_2.model" not in artifacts


def test_architecture_boundaries_remain_one_way() -> None:
    stage_modules = [data, indicators, labels, splits, models, signals, portfolios]

    for module in stage_modules:
        source = inspect.getsource(module)
        assert "provenance.recorder" not in source
        assert "RunRecorder" not in source

    for module in [manifest, artifacts]:
        source = inspect.getsource(module)
        assert "aegis_research.validation" not in source
        assert "aegis_research.portfolios" not in source
        assert "aegis_research.labels" not in source
