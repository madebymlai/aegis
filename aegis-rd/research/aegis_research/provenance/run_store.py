from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.aegis_research.provenance.recorder import RunRecorder


class RunCollisionError(FileExistsError):
    pass


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RunStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)

    def start_run(
        self,
        *,
        config: dict[str, Any],
        run_id: str | None = None,
    ) -> RunRecorder:
        _assert_relative_run_root_safe(self.root_dir)
        physical_run_id = _validate_run_id(run_id or _new_run_id(str(config["name"])))
        run_dir = self.root_dir / physical_run_id
        _assert_run_dir_within_root(self.root_dir, run_dir)
        if run_dir.exists():
            raise RunCollisionError(f"Run already exists: {run_dir}")

        return RunRecorder.start(
            run_dir=run_dir,
            run_id=physical_run_id,
            config=config,
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


def _assert_relative_run_root_safe(root_dir: Path) -> None:
    if root_dir.is_absolute():
        return
    current = Path.cwd()
    for part in root_dir.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("run root must not contain symlinked path components")
    project_root = Path.cwd().resolve(strict=False)
    resolved_root = (Path.cwd() / root_dir).resolve(strict=False)
    if resolved_root != project_root and project_root not in resolved_root.parents:
        raise ValueError("run root must resolve inside the project root")
