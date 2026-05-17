from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from research.aegis_research import model_export as model_export_module
from research.aegis_research.config import load_experiment_config, resolve_experiment_config
from research.aegis_research.experiments import run_experiment
from research.aegis_research.model_export import (
    MODEL_EXPORT_BUNDLE_SCHEMA_VERSION,
    ModelExportError,
    export_model_bundle,
)
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file
from tests.research.aegis_research.model_plugin_fixtures import make_model_registry


def test_model_export_bundle_contains_prediction_contract(tmp_path: Path) -> None:
    run_dir = _run_experiment(tmp_path)
    bundle_dir = export_model_bundle(
        run_dir,
        model_artifact_id="validation.split_0.model",
        output_dir=tmp_path / "exported-model",
    )

    payload = json.loads((bundle_dir / "model_export_bundle.json").read_text())

    assert payload["schema_version"] == MODEL_EXPORT_BUNDLE_SCHEMA_VERSION
    assert payload["mode"] == "prediction_only"
    assert payload["immutable"] is True
    assert payload["source_model_artifact"]["role"] == "validation_model_state"
    assert payload["model_metadata"]["probability"]["output_name"] == "positive_class_probability"
    assert payload["model_metadata"]["probability"]["calibrated"] is False
    assert set(payload["model_metadata"]["diagnostics"]) == {"dataset"}
    assert payload["consumer_contract"]["must_register_plugin_id"] == "tests.sklearn_logistic"
    assert payload["consumer_contract"]["native_state_loading_is_trusted_code"] is True
    assert (bundle_dir / "native" / "model_state.pkl").exists()
    assert "/home/" not in json.dumps(payload)


def test_model_export_rejects_existing_output_directory(tmp_path: Path) -> None:
    run_dir = _run_experiment(tmp_path)
    output_dir = tmp_path / "exported-model"
    export_model_bundle(
        run_dir,
        model_artifact_id="validation.split_0.model",
        output_dir=output_dir,
    )

    with pytest.raises(ModelExportError, match="immutable"):
        export_model_bundle(
            run_dir,
            model_artifact_id="validation.split_0.model",
            output_dir=output_dir,
        )


def test_model_export_rejects_incomplete_model_artifact(tmp_path: Path) -> None:
    run_dir = _run_experiment(tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for artifact in manifest["artifacts"]:
        if artifact["id"] == "validation.split_0.model":
            artifact["status"] = "failed"
            break
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(ModelExportError, match="not completed"):
        export_model_bundle(
            run_dir,
            model_artifact_id="validation.split_0.model",
            output_dir=tmp_path / "exported-model",
        )


def test_model_export_rejects_untrusted_native_state(tmp_path: Path) -> None:
    run_dir = _run_experiment(tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
    metadata_artifact = artifacts["validation.split_0.model.metadata"]
    metadata_path = run_dir / metadata_artifact["path"]
    payload = json.loads(metadata_path.read_text())
    payload["metadata"]["trusted_loading"]["trusted_native_state"] = False
    _rewrite_json_artifact(metadata_path, metadata_artifact, payload)
    atomic_write_json(manifest_path, manifest)

    with pytest.raises(ModelExportError, match="not trusted"):
        export_model_bundle(
            run_dir,
            model_artifact_id="validation.split_0.model",
            output_dir=tmp_path / "exported-model",
        )


def test_model_export_failure_does_not_leave_immutable_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_experiment(tmp_path)
    output_dir = tmp_path / "exported-model"

    def fail_copy(*_args, **_kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(model_export_module.shutil, "copy2", fail_copy)

    with pytest.raises(OSError, match="copy failed"):
        export_model_bundle(
            run_dir,
            model_artifact_id="validation.split_0.model",
            output_dir=output_dir,
        )

    assert not output_dir.exists()
    monkeypatch.undo()
    export_model_bundle(
        run_dir,
        model_artifact_id="validation.split_0.model",
        output_dir=output_dir,
    )
    assert (output_dir / "model_export_bundle.json").exists()


def _run_experiment(tmp_path: Path) -> Path:
    registry = make_model_registry()
    resolved = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml",
        model_registry=registry,
    )
    resolved = resolve_experiment_config(
        replace(resolved.config, output_dir=str(tmp_path / "runs")),
        model_registry=registry,
    )
    result = run_experiment(resolved, run_id="export-source-run")
    return Path(result["run_dir"])


def _rewrite_json_artifact(path: Path, artifact: dict[str, object], payload: dict[str, object]) -> None:
    atomic_write_json(path, payload)
    artifact["hash"] = hash_file(path)
    artifact["size"] = path.stat().st_size
