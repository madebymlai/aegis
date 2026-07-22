"""Shared test doubles for pipeline-stage unit tests.

These stand-ins let pipeline-stage tests construct the minimal recorder and
manifest surfaces they read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FakeManifest:
    """Stand-in for the run manifest surface pipeline stages read and mark."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.status = "running"
        self.started_at = "2025-01-01T00:00:00Z"
        self.finished_at: str | None = None
        self.evidence: dict[str, Any] = {}


class FakeRecorder:
    """Stand-in for ``RunRecorder``.

    ``run_dir`` is optional: publishing reads only ``manifest``; completion
    also reads ``run_dir``/``manifest_path`` and marks the run completed.
    """

    def __init__(self, run_id: str, run_dir: Path | None = None) -> None:
        self.manifest = FakeManifest(run_id)
        self.run_dir = run_dir
        self.manifest_path = run_dir / "manifest.json" if run_dir is not None else None

    def persist(self) -> None:
        pass

    def mark_run_completed(self) -> None:
        self.manifest.status = "completed"
        self.manifest.finished_at = "2025-01-01T01:00:00Z"
        self.persist()

    def run_refs(self) -> dict[str, Any]:
        return {
            "run_id": self.manifest.run_id,
            "run_dir": str(self.run_dir) if self.run_dir is not None else "",
            "manifest_path": str(self.manifest_path) if self.manifest_path is not None else "",
            "status": self.manifest.status,
            "started_at": self.manifest.started_at,
            "finished_at": self.manifest.finished_at,
        }
