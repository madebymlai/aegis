from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from research.aegis_research.canonical_json import to_builtin

MANIFEST_SCHEMA_VERSION = 6


class RunStatus:
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunStage(StrEnum):
    RUN = "run"
    DATA = "data"
    SETUP = "setup"
    PREFLIGHT = "preflight"
    EXECUTION = "execution"
    PUBLISHING = "publishing"
    COMPLETION = "completion"


@dataclass(frozen=True)
class RunFailure:
    stage: RunStage
    error_type: str
    message: str


class ManifestValidationError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class RunManifest:
    run_id: str
    config: dict[str, Any]
    status: str = RunStatus.RUNNING
    started_at: str = field(default_factory=_utc_now)
    finished_at: str | None = None
    failure: RunFailure | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(
        cls,
        *,
        run_id: str,
        config: dict[str, Any],
    ) -> RunManifest:
        return cls(
            run_id=run_id,
            config=to_builtin(config),
        )

    def to_dict(self) -> dict[str, Any]:
        run = {
            "id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.failure is not None:
            run["failure"] = to_builtin(self.failure)
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run": run,
            "config": to_builtin(self.config),
            "evidence": to_builtin(self.evidence),
        }


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError("unsupported manifest schema_version")
