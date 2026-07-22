"""Durable, content-addressed file I/O for artifact persistence.

``write_json`` / ``write_new_json``: serialize a payload to stable JSON and
atomically replace or exclusively create a path (commands).
``hash_file``: return the hex-encoded SHA-256 digest of a file (query).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from research.aegis_research.canonical_json import canonical_json_bytes


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Serialize *payload* to stable UTF-8 JSON and atomically write to *path*.

    On failure, any existing file at *path* is left intact.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = canonical_json_bytes(payload, indent=2)
    _atomic_write(target, json_bytes)


def write_new_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Atomically create a canonical JSON file without replacing an existing path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = canonical_json_bytes(payload, indent=2)
    _atomic_create(target, json_bytes)


def hash_file(path: str | Path) -> str:
    """Return the hex-encoded SHA-256 digest of the file at *path*."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(target: Path, data: bytes) -> None:
    """Durably write *data* to *target* via a temp-file-and-rename dance.

    Recipe: write to a ``.{name}.*.tmp`` file in the target directory,
    chmod 0600, flush+fsync the data, atomically ``replace``, then fsync
    the parent directory.  On failure the temp file is removed and
    *target* is left intact.
    """
    temp_path = _write_temp_file(target, data)
    try:
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_create(target: Path, data: bytes) -> None:
    """Publish complete bytes at an unclaimed path, failing if it already exists."""
    temp_path = _write_temp_file(target, data)
    try:
        os.link(temp_path, target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_temp_file(target: Path, data: bytes) -> Path:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            temp_path.chmod(0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise
    else:
        return temp_path


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
