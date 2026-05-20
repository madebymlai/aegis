from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from research.aegis_research.data import assert_public_metadata_safe
from research.aegis_research.models import MODEL_METADATA_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    atomic_write_json,
    validate_manifest,
)

MODEL_EXPORT_BUNDLE_SCHEMA_VERSION = "model_export_bundle.v1"


class ModelExportError(ValueError):
    pass


def export_model_bundle(
    run_dir: str | Path,
    *,
    model_artifact_id: str,
    output_dir: str | Path,
) -> Path:
    run_path = Path(run_dir)
    bundle_path = Path(output_dir)
    if bundle_path.exists():
        raise ModelExportError(
            "export bundle output_dir already exists; model exports are immutable"
        )

    manifest = _load_manifest(run_path)
    artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
    model_artifact = _completed_artifact(artifacts, model_artifact_id)
    if model_artifact.get("role") != "validation_model_state":
        raise ModelExportError("model artifact is not a validation model state artifact")

    metadata_artifact_id = model_artifact.get("metadata", {}).get("metadata_artifact_id")
    if not metadata_artifact_id:
        raise ModelExportError("model artifact is missing metadata sidecar binding")
    metadata_artifact = _completed_artifact(artifacts, str(metadata_artifact_id))
    metadata_payload = _read_json_artifact(run_path, metadata_artifact)
    model_metadata = metadata_payload.get("metadata")
    if not isinstance(model_metadata, dict):
        raise ModelExportError("model metadata sidecar is malformed")
    if model_metadata.get("schema_version") != MODEL_METADATA_SCHEMA_VERSION:
        raise ModelExportError("unsupported model metadata schema_version")
    trusted_loading = model_metadata["trusted_loading"]
    if not trusted_loading.get("trusted_native_state"):
        raise ModelExportError("model native state is not trusted for export")

    native_path = run_path / model_artifact["path"]

    bundle_payload = {
        "schema_version": MODEL_EXPORT_BUNDLE_SCHEMA_VERSION,
        "mode": "prediction_only",
        "immutable": True,
        "source_run": manifest["run"],
        "source_model_artifact": _artifact_reference(model_artifact),
        "source_model_metadata_artifact": _artifact_reference(metadata_artifact),
        "model_metadata": model_metadata,
        "native_state": {
            "bundle_path": "native/model_state.pkl",
            "trusted_loading": trusted_loading,
            "hash_algorithm": model_artifact["hash_algorithm"],
            "hash": model_artifact["hash"],
            "size": model_artifact["size"],
        },
        "consumer_contract": {
            "must_register_plugin_id": model_metadata["plugin"]["id"],
            "must_match_plugin_version": model_metadata["plugin"]["version"],
            "must_validate_registry_fingerprint": model_metadata["registry_fingerprint"],
            "must_validate_feature_columns_hash": model_metadata["features"]["columns_hash"],
            "probability_output_name": model_metadata["probability"]["output_name"],
            "calibrated": model_metadata["probability"]["calibrated"],
            "native_state_loading_is_trusted_code": True,
        },
    }
    assert_public_metadata_safe(bundle_payload)

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=bundle_path.parent,
        prefix=f".{bundle_path.name}.",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        native_bundle_path = temp_path / "native" / "model_state.pkl"
        native_bundle_path.parent.mkdir(parents=True)
        shutil.copy2(native_path, native_bundle_path)
        atomic_write_json(temp_path / "model_export_bundle.json", bundle_payload)
        temp_path.replace(bundle_path)
    return bundle_path


def _load_manifest(run_path: Path) -> dict[str, Any]:
    manifest_path = run_path / "manifest.json"
    if not manifest_path.exists():
        raise ModelExportError("run manifest is missing")
    payload = json.loads(manifest_path.read_text())
    validate_manifest(payload, run_dir=run_path)
    return payload


def _completed_artifact(
    artifacts: dict[str, dict[str, Any]],
    artifact_id: str,
) -> dict[str, Any]:
    artifact = artifacts.get(artifact_id)
    if artifact is None:
        raise ModelExportError(f"unknown artifact id: {artifact_id}")
    if artifact.get("status") != ArtifactStatus.COMPLETED:
        raise ModelExportError(f"artifact is not completed: {artifact_id}")
    return artifact


def _read_json_artifact(run_path: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("type") != "json":
        raise ModelExportError("model metadata artifact is not JSON")
    return json.loads((run_path / artifact["path"]).read_text())


def _artifact_reference(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": artifact["id"],
        "role": artifact["role"],
        "schema_version": artifact["schema_version"],
        "path": artifact["path"],
        "hash_algorithm": artifact["hash_algorithm"],
        "hash": artifact["hash"],
        "size": artifact["size"],
        "visibility": artifact["visibility"],
    }
