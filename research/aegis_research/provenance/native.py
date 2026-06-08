from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research.aegis_research.provenance.artifacts import ArtifactRegistry
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    RunManifest,
    atomic_write_json,
    normalize_artifact_path,
)


class NativeArtifactWriter:
    def __init__(
        self,
        manifest: RunManifest,
        run_dir: str | Path,
        *,
        persist: Callable[[], None] | None = None,
    ) -> None:
        self.manifest = manifest
        self.run_dir = Path(run_dir)
        self.registry = ArtifactRegistry(manifest, self.run_dir, persist=persist)

    def write_native_artifact(
        self,
        *,
        artifact_id: str,
        role: str,
        producer_stage: str,
        path: str,
        obj: Any,
        schema_version: str = "native.v1",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        path = normalize_artifact_path(path)
        final_path = self.run_dir / path
        if final_path.exists():
            raise FileExistsError(f"Native artifact path already exists: {final_path}")

        sidecar_id = f"{artifact_id}.metadata"
        sidecar_path = f"{path}.metadata.json"
        self.registry.plan_artifact(
            artifact_id=artifact_id,
            role=role,
            artifact_type="native_vectorbt",
            producer_stage=producer_stage,
            path=path,
            schema_version=schema_version,
            upstream_artifact_ids=[sidecar_id],
            metadata={"metadata_artifact_id": sidecar_id},
        )
        self.registry.plan_artifact(
            artifact_id=sidecar_id,
            role=f"{role}_metadata",
            artifact_type="json",
            producer_stage=producer_stage,
            path=sidecar_path,
            schema_version="native_metadata.v1",
            metadata={"native_artifact_id": artifact_id},
        )

        self.registry.begin_artifact_write(artifact_id)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _temp_path(final_path)
        try:
            _save_native_object(obj, temp_path)
            content_hash, size = _hash_native_artifact(temp_path)
            temp_path.replace(final_path)
            _fsync_parent(final_path)

            sidecar_payload = {
                "schema_version": "native_metadata.v1",
                "artifact_id": artifact_id,
                "object_type": f"{type(obj).__module__}.{type(obj).__qualname__}",
                "native_artifact_path": path,
                "metadata": metadata or {},
            }
            self.registry.begin_artifact_write(sidecar_id)
            sidecar_full_path = self.run_dir / sidecar_path
            atomic_write_json(sidecar_full_path, sidecar_payload)
            self.registry.complete_existing_file(sidecar_id)
            self.registry.complete_artifact(
                artifact_id,
                content_hash=content_hash,
                size=size,
                metadata={"metadata_artifact_id": sidecar_id, **(metadata or {})},
            )
        except Exception as error:
            if temp_path.exists():
                temp_path.unlink()
            if final_path.exists() and not any(
                artifact["id"] == artifact_id and artifact["status"] == "completed"
                for artifact in self.manifest.artifacts
            ):
                final_path.unlink()
            self._fail_uncompleted_artifact(
                sidecar_id,
                {"error_type": type(error).__name__, "message": "native metadata write failed"},
            )
            self.registry.fail_artifact(
                artifact_id,
                {"error_type": type(error).__name__, "message": "native artifact write failed"},
            )
            raise

    def _fail_uncompleted_artifact(self, artifact_id: str, diagnostic: dict[str, str]) -> None:
        artifact = next(
            (artifact for artifact in self.manifest.artifacts if artifact["id"] == artifact_id),
            None,
        )
        if artifact is not None and artifact["status"] != ArtifactStatus.COMPLETED:
            self.registry.fail_artifact(artifact_id, diagnostic)


def _save_native_object(obj: Any, path: Path) -> None:
    if hasattr(obj, "save"):
        obj.save(path)
        return
    with path.open("wb") as handle:
        pickle.dump(obj, handle)


def _hash_native_artifact(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _temp_path(final_path: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=final_path.parent,
        prefix=f"tmp_{final_path.stem}_",
        suffix=final_path.suffix,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    temp_path.chmod(0o600)
    return temp_path


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
