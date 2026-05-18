from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from research.aegis_research.cli_support.errors import (
    DefaultResolutionError,
    DefaultStorageError,
    MissingDefaultError,
)
from research.aegis_research.config import load_experiment_config
from research.aegis_research.model_registry import FrozenModelRegistry, ModelRegistry

DEFAULT_STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_NAME = "aerd-default.json"


@dataclass(frozen=True)
class WorktreeDefaultStore:
    root: Path
    state_path: Path


@dataclass(frozen=True)
class DefaultSelection:
    config_path: Path
    display_path: str
    source: str = "local_default"

    def summary(self) -> dict[str, str]:
        return {"source": self.source, "config_path": self.display_path}


def set_default(
    config_path: str | Path,
    *,
    model_registry: ModelRegistry | FrozenModelRegistry | None,
    cwd: str | Path | None = None,
) -> DefaultSelection:
    store = default_store(cwd=cwd)
    selection = _selection_from_path(config_path, store)
    resolved = load_experiment_config(selection.config_path, model_registry=model_registry)
    payload = {
        "schema_version": DEFAULT_STATE_SCHEMA_VERSION,
        "selected_config": selection.display_path,
        "validated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "validated_config": {
            "schema_version": resolved.config.schema_version,
            "name": resolved.config.name,
            "raw_config_hash": resolved.raw_config_hash,
        },
    }
    _write_state(store.state_path, payload)
    return selection


def resolve_default(*, cwd: str | Path | None = None) -> DefaultSelection:
    store = default_store(cwd=cwd)
    state = _read_state(store.state_path)
    relative_path = state.get("selected_config")
    if not isinstance(relative_path, str) or not relative_path:
        raise DefaultResolutionError("local default state is missing selected_config")
    if _unsafe_relative_path(relative_path):
        raise DefaultResolutionError("local default state contains an unsafe config path")
    config_path = (store.root / relative_path).resolve(strict=False)
    try:
        config_path.relative_to(store.root.resolve(strict=True))
    except ValueError as error:
        raise DefaultResolutionError("local default config path escapes the worktree") from error
    if not config_path.is_file():
        raise DefaultResolutionError("local default experiment config does not exist")
    return DefaultSelection(config_path=config_path, display_path=relative_path)


def default_store(*, cwd: str | Path | None = None) -> WorktreeDefaultStore:
    root = _git(cwd, "rev-parse", "--show-toplevel")
    git_dir = _git(cwd, "rev-parse", "--absolute-git-dir")
    if root is None or git_dir is None:
        raise DefaultResolutionError("local experiment defaults require a git worktree")
    return WorktreeDefaultStore(
        root=Path(root).resolve(strict=True),
        state_path=Path(git_dir).resolve(strict=False) / "info" / DEFAULT_STATE_NAME,
    )


def _selection_from_path(config_path: str | Path, store: WorktreeDefaultStore) -> DefaultSelection:
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = store.root / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise DefaultResolutionError("experiment config does not exist") from error
    try:
        relative = resolved.relative_to(store.root.resolve(strict=True))
    except ValueError as error:
        raise DefaultResolutionError("local defaults can only point at configs inside the worktree") from error
    if not resolved.is_file():
        raise DefaultResolutionError("experiment config is not a file")
    display_path = relative.as_posix()
    if _unsafe_relative_path(display_path):
        raise DefaultResolutionError("experiment config path is unsafe")
    return DefaultSelection(config_path=resolved, display_path=display_path)


def _read_state(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as error:
        raise MissingDefaultError("no local experiment default is configured") from error
    except IsADirectoryError as error:
        raise DefaultStorageError("local default state path is a directory") from error
    except PermissionError as error:
        raise DefaultStorageError("local default state is not readable") from error
    except json.JSONDecodeError as error:
        raise DefaultResolutionError("local default state is not valid JSON") from error
    except OSError as error:
        raise DefaultStorageError("local default state could not be read") from error
    if not isinstance(payload, dict):
        raise DefaultResolutionError("local default state must be a JSON object")
    if payload.get("schema_version") != DEFAULT_STATE_SCHEMA_VERSION:
        raise DefaultResolutionError("local default state has unsupported schema_version")
    return payload


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, allow_nan=False, sort_keys=True, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            temp_path.chmod(0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
        _fsync_parent(path)
    except OSError as error:
        raise DefaultStorageError("local default state could not be written") from error
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _git(cwd: str | Path | None, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _unsafe_relative_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return pure_path.is_absolute() or not path or any(part == ".." for part in pure_path.parts)
