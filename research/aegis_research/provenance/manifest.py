from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from research.aegis_research.atomic_write import hash_file
from research.aegis_research.canonical_json import to_builtin

MANIFEST_SCHEMA_VERSION = 4


class RunStatus:
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    STALE = "stale"
    SUPERSEDED = "superseded"


class StageStatus:
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ArtifactStatus:
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ManifestValidationError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class RunManifest:
    run_id: str
    run_dir: Path
    run_label: str
    mode: str
    config: dict[str, Any]
    status: str = RunStatus.RUNNING
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        *,
        run_id: str,
        run_dir: str | Path,
        run_label: str,
        mode: str,
        config: dict[str, Any],
        lineage: dict[str, Any] | None = None,
    ) -> RunManifest:
        return cls(
            run_id=run_id,
            run_dir=Path(run_dir),
            run_label=run_label,
            mode=mode,
            config=to_builtin(config),
            lineage=to_builtin(lineage or {}),
        )

    def add_stage(self, stage_id: str, status: str, **metadata: Any) -> None:
        record = {
            "id": stage_id,
            "status": status,
            "updated_at": _utc_now(),
            **to_builtin(metadata),
        }
        for index, stage in enumerate(self.stages):
            if stage["id"] == stage_id:
                self.stages[index] = {**stage, **record}
                return
        self.stages.append(record)

    def add_artifact(
        self,
        *,
        artifact_id: str,
        role: str,
        artifact_type: str,
        producer_stage: str,
        path: str,
        schema_version: str,
        status: str,
        content_hash: str | None = None,
        size: int | None = None,
        shape: dict[str, Any] | None = None,
        upstream_artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_path = normalize_artifact_path(path)
        _validate_artifact_completion(status, content_hash, size)
        if any(artifact["id"] == artifact_id for artifact in self.artifacts):
            raise ManifestValidationError(f"duplicate artifact id: {artifact_id}")
        if any(artifact["path"] == normalized_path for artifact in self.artifacts):
            raise ManifestValidationError(f"duplicate artifact path: {normalized_path}")

        artifact = {
            "id": artifact_id,
            "role": role,
            "type": artifact_type,
            "producer_stage": producer_stage,
            "path": normalized_path,
            "hash_algorithm": "sha256",
            "hash": content_hash,
            "size": size,
            "schema_version": schema_version,
            "status": status,
            "shape": to_builtin(shape or {}),
            "upstream_artifact_ids": list(upstream_artifact_ids or []),
            "metadata": to_builtin(metadata or {}),
            "updated_at": _utc_now(),
        }
        self.artifacts.append(artifact)
        return artifact

    def replace_artifact(self, artifact_id: str, artifact: dict[str, Any]) -> None:
        normalized_path = normalize_artifact_path(str(artifact.get("path", "")))
        _validate_artifact_completion(
            artifact.get("status"), artifact.get("hash"), artifact.get("size")
        )
        for index, existing in enumerate(self.artifacts):
            if existing["id"] == artifact_id:
                if any(
                    other["id"] != artifact_id and other["path"] == normalized_path
                    for other in self.artifacts
                ):
                    raise ManifestValidationError(f"duplicate artifact path: {normalized_path}")
                artifact["path"] = normalized_path
                self.artifacts[index] = to_builtin(artifact)
                return
        raise ManifestValidationError(f"unknown artifact id: {artifact_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run": {
                "id": self.run_id,
                "label": self.run_label,
                "status": self.status,
                "mode": self.mode,
                "run_dir": self.run_id,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            },
            "config": to_builtin(self.config),
            "evidence": to_builtin(self.evidence),
            "lineage": to_builtin(self.lineage),
            "stages": to_builtin(self.stages),
            "artifacts": to_builtin(self.artifacts),
        }


def validate_manifest(payload: dict[str, Any], *, run_dir: str | Path | None = None) -> None:
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError("unsupported manifest schema_version")
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ManifestValidationError("artifacts must be a list")

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    artifacts_by_id: dict[str, dict[str, Any]] = {}
    root = Path(run_dir) if run_dir is not None else None
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if artifact_id in seen_ids:
            raise ManifestValidationError(f"duplicate artifact id: {artifact_id}")
        seen_ids.add(artifact_id)
        artifacts_by_id[str(artifact_id)] = artifact

        path = normalize_artifact_path(str(artifact.get("path", "")))
        if path in seen_paths:
            raise ManifestValidationError(f"duplicate artifact path: {path}")
        seen_paths.add(path)

        status = artifact.get("status")
        _validate_artifact_completion(status, artifact.get("hash"), artifact.get("size"))
        if status == ArtifactStatus.COMPLETED and root is not None:
            artifact_path = root / path
            if not artifact_path.exists():
                raise ManifestValidationError(
                    f"completed artifact is missing: {artifact.get('id')}"
                )
            _validate_file_identity(artifact, artifact_path)

    for artifact in artifacts:
        if artifact.get("status") != ArtifactStatus.COMPLETED:
            continue
        for upstream_id in artifact.get("upstream_artifact_ids", []):
            upstream = artifacts_by_id.get(str(upstream_id))
            if upstream is None:
                raise ManifestValidationError(f"missing upstream artifact: {upstream_id}")
            if upstream.get("status") != ArtifactStatus.COMPLETED:
                raise ManifestValidationError(f"incomplete upstream artifact: {upstream_id}")


def normalize_artifact_path(path: str) -> str:
    pure_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    if (
        pure_path.is_absolute()
        or windows_path.is_absolute()
        or path.startswith("~")
        or not path
        or any(part == ".." for part in pure_path.parts)
    ):
        raise ManifestValidationError("artifact path must be run-relative and normalized")
    normalized = pure_path.as_posix()
    if normalized in {".", ""}:
        raise ManifestValidationError("artifact path must be run-relative and normalized")
    return normalized


def _validate_artifact_completion(
    status: str | None,
    content_hash: str | None,
    size: int | None,
) -> None:
    if status != ArtifactStatus.COMPLETED:
        return
    if not content_hash:
        raise ManifestValidationError("completed artifact requires hash")
    if size is None:
        raise ManifestValidationError("completed artifact requires size")
    if size < 0:
        raise ManifestValidationError("completed artifact size must be non-negative")


def _validate_file_identity(artifact: dict[str, Any], path: Path) -> None:
    if artifact.get("size") != path.stat().st_size:
        raise ManifestValidationError(f"artifact size mismatch: {artifact.get('id')}")
    if artifact.get("hash") != hash_file(path):
        raise ManifestValidationError(f"artifact hash mismatch: {artifact.get('id')}")
