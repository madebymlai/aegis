from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.aegis_research.atomic_write import write_json
from research.aegis_research.provenance.artifacts import ArtifactRegistry
from research.aegis_research.provenance.manifest import (
    RunManifest,
    RunStatus,
    StageStatus,
)


class RerunMode:
    NEW = "new"
    DUPLICATE = "duplicate"
    FORK = "fork"
    OVERWRITE = "overwrite"


class RunRecorder:
    def __init__(self, manifest: RunManifest) -> None:
        self.manifest = manifest
        self.run_dir = manifest.run_dir
        self.manifest_path = self.run_dir / "manifest.json"
        self.artifacts = ArtifactRegistry(manifest, self.run_dir, persist=self.persist)

    @classmethod
    def start(
        cls,
        *,
        run_dir: str | Path,
        run_id: str,
        run_label: str,
        mode: str,
        config: dict[str, Any],
        lineage: dict[str, Any] | None = None,
    ) -> RunRecorder:
        path = Path(run_dir)
        path.mkdir(parents=True, exist_ok=False, mode=0o700)
        manifest = RunManifest.new(
            run_id=run_id,
            run_dir=path,
            run_label=run_label,
            mode=mode,
            config=config,
            lineage=lineage,
        )
        recorder = cls(manifest)
        recorder.persist()
        return recorder

    def persist(self) -> None:
        write_json(self.manifest_path, self.manifest.to_dict())

    def mark_stage(self, stage_id: str, status: str, **metadata: Any) -> None:
        self.manifest.add_stage(stage_id, status, **metadata)
        self.persist()

    def mark_run_completed(self) -> None:
        self.manifest.status = RunStatus.COMPLETED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def mark_run_failed(
        self,
        *,
        stage_id: str = "run",
        diagnostic: dict[str, Any] | None = None,
    ) -> None:
        self.manifest.add_stage(stage_id, StageStatus.FAILED, diagnostic=diagnostic or {})
        self.manifest.status = RunStatus.FAILED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def mark_run_interrupted(
        self,
        *,
        stage_id: str = "run",
        diagnostic: dict[str, Any] | None = None,
    ) -> None:
        self.manifest.add_stage(stage_id, StageStatus.FAILED, diagnostic=diagnostic or {})
        self.manifest.status = RunStatus.INTERRUPTED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def run_refs(self) -> dict[str, Any]:
        """Return a snapshot of the current Manifest state (run_id, status, timestamps, paths)."""
        return {
            "run_id": self.manifest.run_id,
            "run_dir": str(self.run_dir),
            "manifest_path": str(self.manifest_path),
            "status": self.manifest.status,
            "started_at": self.manifest.started_at,
            "finished_at": self.manifest.finished_at,
        }

    def _now_from_manifest(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
