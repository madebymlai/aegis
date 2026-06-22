from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from research.aegis_research.atomic_write import hash_file
from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.configuration import (
    ResolvedRunConfig,
    to_builtin,
)

SAFE_ENV_KEYS = ("LANG", "LC_ALL", "TZ", "PYTHONHASHSEED")
PACKAGE_NAMES = (
    "vectorbtpro",
    "pandas",
    "numpy",
    "numba",
    "pyyaml",
    "aegis-rd",
)
VBT_SETTINGS_SECTIONS = (
    "data",
    "portfolio",
    "returns",
    "splitter",
    "signals",
    "numba",
    "jitting",
    "chunking",
    "caching",
    "pickling",
)


def capture_run_start_evidence(
    config: ResolvedRunConfig,
    *,
    repo_path: str | Path,
) -> dict[str, Any]:
    return {
        "config": capture_config_evidence(config),
        "environment": capture_environment_evidence(),
        "repository": capture_git_evidence(repo_path),
        "packages": capture_package_versions(),
        "vectorbt_settings": capture_vectorbt_settings(),
    }


def capture_config_evidence(config: ResolvedRunConfig) -> dict[str, Any]:
    evidence = {
        "schema_version": config.config.schema_version,
        "source_path": config.source_path,
        "authored_config_hash": canonical_hash(config.authored_config_document()),
        "resolved_config_hash": canonical_hash(config.resolved_config_document()),
        "raw_config_identity": {"hash": config.raw_config_hash},
    }
    if config.selection is not None:
        evidence["selection"] = dict(config.selection.manifest())
    return evidence


def capture_environment_evidence() -> dict[str, Any]:
    variables = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    return {
        "allowlist": list(SAFE_ENV_KEYS),
        "variables": variables,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


def capture_git_evidence(repo_path: str | Path) -> dict[str, Any]:
    root = Path(repo_path)
    commit = _git(root, "rev-parse", "HEAD")
    if commit is None:
        return {"available": False, "reason": "not a git checkout"}
    branch = _git(root, "branch", "--show-current") or "detached"
    remote = _git(root, "config", "--get", "remote.origin.url")
    untracked_files = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    changed_files = (
        _git_lines(root, "diff", "--name-only")
        + _git_lines(root, "diff", "--cached", "--name-only")
        + untracked_files
    )
    diff = "\n".join(
        [
            _git(root, "diff", "--binary") or "",
            _git(root, "diff", "--cached", "--binary") or "",
            _untracked_content_identity(root, untracked_files),
        ]
    )
    return {
        "available": True,
        "commit": commit,
        "branch": branch,
        "dirty": bool(changed_files),
        "changed_files": sorted(set(changed_files)),
        "diff_hash": hashlib.sha256(diff.encode()).hexdigest(),
        "remote": remote if remote else None,
    }


def capture_package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package_name in PACKAGE_NAMES:
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = None
    return versions


def capture_vectorbt_settings() -> dict[str, Any]:
    try:
        from vectorbtpro import vbt
    except Exception:
        return {"available": False}

    settings = {}
    for section in VBT_SETTINGS_SECTIONS:
        try:
            settings[section] = _jsonable_value(to_builtin(vbt.settings[section]))
        except Exception:
            settings[section] = {"available": False}
    return {"available": True, "sections": settings}


def canonical_hash(value: Any) -> str:
    json_safe_value = to_builtin(value)
    return hashlib.sha256(canonical_json_bytes(json_safe_value)).hexdigest()


def _jsonable_value(value: Any) -> Any:
    if value is None or isinstance(value, int | float | bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable_value(item) for item in value]
    return {"available": False, "type": type(value).__name__}


def _git(repo_path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def _git_lines(repo_path: Path, *args: str) -> list[str]:
    output = _git(repo_path, *args)
    if not output:
        return []
    return [line for line in output.splitlines() if line]


def _untracked_content_identity(repo_path: Path, paths: list[str]) -> str:
    records = []
    for relative_path in sorted(paths):
        path = repo_path / relative_path
        if path.is_file():
            records.append({"path": relative_path, "sha256": hash_file(path)})
        else:
            records.append({"path": relative_path, "type": "non-file"})
    return canonical_json_bytes(records).decode()
