"""Durable, content-addressed file I/O for artifact persistence.

A deep root-level leaf (beside canonical_json.py) serving provenance/*
and optimization/*. Public interface: free functions over paths.

``write_json`` is a command (serialize + durable atomic write).
``hash_file`` is a query (content-addressed digest).
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

    The on-disk recipe: write to a hidden ``.{name}.*.tmp`` temp file in the
    target directory, chmod 0600, write+flush+fsync the data fd, atomic
    ``replace``, and fsync the parent directory.  On failure the temp file is
    removed and any existing target is left intact.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = canonical_json_bytes(payload, indent=2)
    _atomic_write(target, json_bytes)


def hash_file(path: str | Path) -> str:
    """Return the hex-encoded SHA-256 digest of the file at *path*."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── private durability recipe ────────────────────────────────────────────────


def _atomic_write(target: Path, data: bytes) -> None:
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
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
