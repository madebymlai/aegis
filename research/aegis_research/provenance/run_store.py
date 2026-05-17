from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.aegis_research.provenance.recorder import RerunMode, RunRecorder


class RunCollisionError(FileExistsError):
    pass


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RunStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def start_run(
        self,
        *,
        run_label: str,
        config: dict[str, Any],
        mode: str = RerunMode.NEW,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        supersedes_run_id: str | None = None,
    ) -> RunRecorder:
        if mode not in {
            RerunMode.NEW,
            RerunMode.DUPLICATE,
            RerunMode.FORK,
            RerunMode.OVERWRITE,
        }:
            raise ValueError(f"Unsupported run mode for new physical run: {mode}")
        if mode == RerunMode.FORK and parent_run_id is None:
            raise ValueError("fork mode requires parent_run_id")
        if mode == RerunMode.OVERWRITE and supersedes_run_id is None:
            raise ValueError("overwrite mode requires supersedes_run_id")

        physical_run_id = _validate_run_id(run_id or _new_run_id(run_label))
        run_dir = self.root_dir / physical_run_id
        _assert_run_dir_within_root(self.root_dir, run_dir)
        if run_dir.exists():
            raise RunCollisionError(f"Run already exists: {run_dir}")

        lineage: dict[str, Any] = {}
        if parent_run_id is not None:
            lineage["parent_run_id"] = parent_run_id
        if supersedes_run_id is not None:
            lineage["supersedes_run_id"] = supersedes_run_id

        return RunRecorder.start(
            run_dir=run_dir,
            run_id=physical_run_id,
            run_label=run_label,
            mode=mode,
            config=config,
            lineage=lineage,
        )


def _new_run_id(run_label: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}_{run_label}"


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id) or run_id in {".", ".."}:
        raise ValueError(
            "run_id must contain only letters, numbers, dots, underscores, and hyphens"
        )
    return run_id


def _assert_run_dir_within_root(root_dir: Path, run_dir: Path) -> None:
    root = root_dir.resolve(strict=False)
    target = run_dir.resolve(strict=False)
    if root not in target.parents:
        raise ValueError("run_id must resolve inside the run root")
