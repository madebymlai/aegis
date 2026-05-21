from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ArtifactVisibility,
    RunManifest,
    validate_manifest,
)
from research.aegis_research.provenance.native import (
    NativeArtifactSafetyError,
    NativeArtifactWriter,
)


def test_native_writer_persists_private_artifact_and_public_metadata(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    writer.write_native_artifact(
        artifact_id="portfolio.split_0.test",
        role="portfolio",
        producer_stage="validation",
        path="native/portfolio.pkl",
        obj=_NativeObject(b"portfolio-bytes"),
        metadata={"split": "split_0", "set": "test"},
    )

    native = next(
        artifact for artifact in manifest.artifacts if artifact["id"] == "portfolio.split_0.test"
    )
    sidecar = next(
        artifact
        for artifact in manifest.artifacts
        if artifact["id"] == "portfolio.split_0.test.metadata"
    )
    assert native["status"] == ArtifactStatus.COMPLETED
    assert native["visibility"] == ArtifactVisibility.PRIVATE
    assert sidecar["status"] == ArtifactStatus.COMPLETED
    assert sidecar["visibility"] == ArtifactVisibility.PUBLIC
    assert sidecar["upstream_artifact_ids"] == []
    assert native["upstream_artifact_ids"] == [sidecar["id"]]
    sidecar_payload = json.loads((tmp_path / sidecar["path"]).read_text())
    assert sidecar_payload["schema_version"] == "native_metadata.v1"
    assert sidecar_payload["metadata"]["split"] == "split_0"
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_native_writer_rejects_path_collision(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)
    target = tmp_path / "native" / "portfolio.pkl"
    target.parent.mkdir()
    target.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        writer.write_native_artifact(
            artifact_id="portfolio",
            role="portfolio",
            producer_stage="validation",
            path="native/portfolio.pkl",
            obj=_NativeObject(b"new"),
        )


def test_native_writer_fails_closed_when_secret_bytes_are_detected(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"token=super-secret-token"),
            known_secrets=["super-secret-token"],
        )

    artifact = next(artifact for artifact in manifest.artifacts if artifact["id"] == "data.remote")
    assert artifact["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()


def test_native_writer_fails_closed_when_secret_like_bytes_are_detected(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"Authorization: Bearer generated-token"),
        )

    artifact = next(artifact for artifact in manifest.artifacts if artifact["id"] == "data.remote")
    assert artifact["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()


def test_native_writer_rejects_secret_public_metadata(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"safe-bytes"),
            metadata={"api_token": "super-secret-token"},
            known_secrets=["super-secret-token"],
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_data_native_writer_rejects_secret_sensitive_object_state(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data_native",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObjectWithSensitiveState(),
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_native_writer_fails_sidecar_when_metadata_write_fails(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(TypeError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"safe-bytes"),
            metadata={"not_json": object()},
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


class _NativeObject:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.payload)


class _NativeObjectWithSensitiveState:
    def __init__(self) -> None:
        self.headers = {"X-Session": "generated-cookie"}

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(b"safe-bytes")
