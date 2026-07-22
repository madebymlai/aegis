from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.aegis_research.atomic_write import write_json
from research.aegis_research.provenance.manifest import (
    RunManifest,
    RunStatus,
)

_FAILURE_MESSAGE_LIMIT = 1000


class RunRecorder:
    def __init__(self, manifest: RunManifest, manifest_path: Path) -> None:
        self.manifest = manifest
        self.manifest_path = manifest_path

    @classmethod
    def start(
        cls,
        *,
        manifest_path: str | Path,
        run_id: str,
        config: dict[str, Any],
    ) -> RunRecorder:
        path = Path(manifest_path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            raise FileExistsError(f"Run already exists: {path}")
        manifest = RunManifest.new(
            run_id=run_id,
            config=config,
        )
        recorder = cls(manifest, path)
        recorder.persist()
        return recorder

    def persist(self) -> None:
        write_json(self.manifest_path, self.manifest.to_dict())

    def mark_run_completed(self) -> None:
        self.manifest.status = RunStatus.COMPLETED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def mark_run_failed(
        self,
        *,
        stage: str,
        error: BaseException,
    ) -> None:
        self.manifest.failure = _terminal_failure(stage, error)
        self.manifest.status = RunStatus.FAILED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def mark_run_interrupted(
        self,
        *,
        stage: str,
        error: BaseException,
    ) -> None:
        self.manifest.failure = _terminal_failure(stage, error)
        self.manifest.status = RunStatus.INTERRUPTED
        self.manifest.finished_at = self._now_from_manifest()
        self.persist()

    def run_refs(self) -> dict[str, Any]:
        """Return a snapshot of the current Manifest state and its durable path."""
        return {
            "run_id": self.manifest.run_id,
            "manifest_path": str(self.manifest_path),
            "status": self.manifest.status,
            "started_at": self.manifest.started_at,
            "finished_at": self.manifest.finished_at,
        }

    def _now_from_manifest(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _terminal_failure(stage: str, error: BaseException) -> dict[str, str]:
    message = str(error)
    if isinstance(error, KeyboardInterrupt) and not message:
        message = "interrupted"
    return {
        "stage": stage,
        "error_type": type(error).__name__,
        "message": message[:_FAILURE_MESSAGE_LIMIT],
    }
