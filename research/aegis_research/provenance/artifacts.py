from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ArtifactVisibility,
    ManifestValidationError,
    RunManifest,
    hash_file,
)


class ArtifactRegistry:
    def __init__(
        self,
        manifest: RunManifest,
        run_dir: str | Path,
        *,
        persist: Callable[[], None] | None = None,
    ) -> None:
        self.manifest = manifest
        self.run_dir = Path(run_dir)
        self._persist_manifest = persist

    def plan_artifact(
        self,
        *,
        artifact_id: str,
        role: str,
        artifact_type: str,
        producer_stage: str,
        path: str,
        schema_version: str,
        visibility: str = ArtifactVisibility.PUBLIC,
        upstream_artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact = self.manifest.add_artifact(
            artifact_id=artifact_id,
            role=role,
            artifact_type=artifact_type,
            producer_stage=producer_stage,
            path=path,
            schema_version=schema_version,
            status=ArtifactStatus.PLANNED,
            visibility=visibility,
            upstream_artifact_ids=upstream_artifact_ids,
            metadata=metadata,
        )
        try:
            self._persist()
        except Exception:
            self.manifest.artifacts = [
                artifact for artifact in self.manifest.artifacts if artifact["id"] != artifact_id
            ]
            raise
        return artifact

    def begin_artifact_write(self, artifact_id: str) -> None:
        artifact = self._artifact(artifact_id)
        if artifact["status"] not in {ArtifactStatus.PLANNED, ArtifactStatus.PARTIAL}:
            raise ManifestValidationError(
                f"artifact {artifact_id} cannot transition to writing from {artifact['status']}"
            )
        self._replace(artifact_id, {**artifact, "status": ArtifactStatus.WRITING})

    def complete_artifact(
        self,
        artifact_id: str,
        *,
        content_hash: str | None = None,
        size: int | None = None,
        shape: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        artifact = self._artifact(artifact_id)
        if artifact["status"] != ArtifactStatus.WRITING:
            raise ManifestValidationError(
                f"artifact {artifact_id} cannot complete from {artifact['status']}"
            )
        artifact_path = self.run_dir / artifact["path"]
        if size is None and artifact_path.exists():
            size = artifact_path.stat().st_size
        completed = {
            **artifact,
            "hash": content_hash,
            "size": size,
            "shape": shape or artifact.get("shape", {}),
            "metadata": {**artifact.get("metadata", {}), **(metadata or {})},
            "status": ArtifactStatus.COMPLETED,
        }
        self._replace(artifact_id, completed)

    def fail_artifact(self, artifact_id: str, diagnostic: dict[str, Any] | None = None) -> None:
        artifact = self._artifact(artifact_id)
        self._replace(
            artifact_id,
            {
                **artifact,
                "status": ArtifactStatus.FAILED,
                "diagnostic": diagnostic or {},
            },
        )

    def mark_artifact_partial(
        self,
        artifact_id: str,
        diagnostic: dict[str, Any] | None = None,
    ) -> None:
        artifact = self._artifact(artifact_id)
        self._replace(
            artifact_id,
            {
                **artifact,
                "status": ArtifactStatus.PARTIAL,
                "diagnostic": diagnostic or {},
            },
        )

    def complete_existing_file(
        self,
        artifact_id: str,
        *,
        shape: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        artifact = self._artifact(artifact_id)
        artifact_path = self.run_dir / artifact["path"]
        self.complete_artifact(
            artifact_id,
            content_hash=hash_file(artifact_path),
            size=artifact_path.stat().st_size,
            shape=shape,
            metadata=metadata,
        )

    def _artifact(self, artifact_id: str) -> dict[str, Any]:
        for artifact in self.manifest.artifacts:
            if artifact["id"] == artifact_id:
                return artifact
        raise ManifestValidationError(f"unknown artifact id: {artifact_id}")

    def _replace(self, artifact_id: str, artifact: dict[str, Any]) -> None:
        previous = copy.deepcopy(self._artifact(artifact_id))
        self.manifest.replace_artifact(artifact_id, artifact)
        try:
            self._persist()
        except Exception:
            self.manifest.replace_artifact(artifact_id, previous)
            raise

    def _persist(self) -> None:
        if self._persist_manifest is not None:
            self._persist_manifest()
