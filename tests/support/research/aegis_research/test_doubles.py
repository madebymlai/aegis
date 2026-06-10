"""Shared test doubles for pipeline-stage unit tests.

These stand-ins replace production types that carry heavy dependencies
(e.g. MarketDataResult, DataArrayContract) so that pipeline-stage tests
can construct the minimal surface each stage reads without importing
the full data or array stack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar


class FakeDataResult:
    """Lightweight stand-in for ``MarketDataResult``.

    ``metadata`` is a ClassVar so every instance surfaces identical
    metadata — tests never mutate it during a stage invocation.
    ``quality`` is an instance attribute so it can hold a simple
    stand-in without pulling in the real quality model.
    """

    metadata: ClassVar[dict[str, Any]] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "timeframe": "1D",
        "loaded_arrays": ["Close", "Open"],
        "shape": (120, 1),
        "index_start": "2020-01-01",
        "index_end": "2020-06-01",
    }

    def __init__(self, *, quality_state: str = "healthy") -> None:
        self.quality = type("_Quality", (), {"state": quality_state})()


class FakeArrayContract:
    """Stand-in for ``DataArrayContract``."""

    def metadata(self) -> dict[str, Any]:
        return {"schema_version": "data_array_contract.v1"}


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
