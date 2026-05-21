from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.config import ResolvedRunConfig
from research.aegis_research.data import MarketDataResult, assert_public_metadata_safe
from research.aegis_research.provenance.manifest import (
    ArtifactVisibility,
    atomic_write_json,
)
from research.aegis_research.provenance.native import NativeArtifactWriter
from research.aegis_research.provenance.recorder import RunRecorder


class ExperimentArtifactWriter:
    def __init__(self, recorder: RunRecorder) -> None:
        self.recorder = recorder
        self.native_writer = NativeArtifactWriter(
            recorder.manifest,
            recorder.run_dir,
            persist=recorder.persist,
        )

    def write_config_artifacts(self, config: ResolvedRunConfig) -> None:
        _write_text_artifact(
            self.recorder,
            artifact_id="config.resolved",
            role="resolved_config",
            producer_stage="config",
            path="config.yaml",
            text=yaml.safe_dump(config.redacted_resolved_config(), sort_keys=False),
            schema_version="resolved_config.v1",
        )
        _write_text_artifact(
            self.recorder,
            artifact_id="config.authored",
            role="authored_config",
            producer_stage="config",
            path="config_authored.yaml",
            text=yaml.safe_dump(config.redacted_authored_config(), sort_keys=False),
            schema_version="authored_config.v1",
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="config.manifest",
            role="config_manifest",
            producer_stage="config",
            path="config_manifest.json",
            payload=config.manifest(),
            schema_version="config_manifest.v1",
            visibility=ArtifactVisibility.PRIVATE,
        )

    def write_data_metadata_artifact(self, data_result: MarketDataResult) -> None:
        assert_public_metadata_safe(
            data_result.metadata,
            known_secrets=data_result.known_secrets,
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="data.metadata",
            role="data_metadata",
            producer_stage="data",
            path="data_metadata.json",
            payload=data_result.metadata,
            schema_version="data_metadata.v2",
        )

    def write_data_native_artifact(self, data_result: MarketDataResult) -> None:
        self.native_writer.write_native_artifact(
            artifact_id="data.native",
            role="data_native",
            producer_stage="data",
            path="native/data.pkl",
            obj=data_result.native_data,
            metadata=data_result.metadata,
            known_secrets=data_result.known_secrets,
        )


def _write_json_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    payload: dict[str, Any],
    schema_version: str,
    upstream_artifact_ids: list[str] | None = None,
    visibility: str = ArtifactVisibility.PUBLIC,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="json",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
        upstream_artifact_ids=upstream_artifact_ids,
        visibility=visibility,
    )
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: atomic_write_json(target, payload),
    )


def _write_text_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    text: str,
    schema_version: str,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="yaml",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
    )
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: _atomic_write_text(target, text),
    )


def _write_csv_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    frame: Any,
    schema_version: str,
    upstream_artifact_ids: list[str] | None = None,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="csv",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
        upstream_artifact_ids=upstream_artifact_ids,
    )
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: _atomic_write_csv(target, frame),
        shape=lambda: {"rows": len(frame), "columns": len(frame.columns)},
    )


def _write_artifact_file(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    path: str,
    write: Callable[[Path], None],
    shape: Callable[[], dict[str, Any]] | None = None,
) -> None:
    target = recorder.run_dir / path
    recorder.artifacts.begin_artifact_write(artifact_id)
    try:
        write(target)
        recorder.artifacts.complete_existing_file(
            artifact_id,
            shape=shape() if shape is not None else None,
        )
    except Exception as error:
        try:
            _fail_artifact_write(recorder, artifact_id=artifact_id, target=target, error=error)
        except Exception as failure_error:
            error.add_note(f"failed to mark artifact {artifact_id!r} as failed: {failure_error}")
        raise


def _fail_artifact_write(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    target: Path,
    error: Exception,
) -> None:
    if target.exists():
        target.unlink()
    recorder.artifacts.fail_artifact(
        artifact_id,
        {"error_type": type(error).__name__, "message": str(error)[:1000]},
    )


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode())


def _atomic_write_csv(path: Path, frame: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(target)
    try:
        frame.to_csv(temp_path)
        _fsync_file(temp_path)
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(target)
    try:
        with temp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _temp_path(target: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        temp_path.chmod(0o600)
    return temp_path


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
