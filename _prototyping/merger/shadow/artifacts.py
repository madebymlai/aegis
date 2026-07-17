"""Immutable artifact primitives shared by the cash-merger shadow."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Serialize a value into stable bytes suitable for content identities."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def write_once(destination: Path, payload: bytes) -> None:
    """Atomically create an immutable artifact, or accept an existing winner."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(FileExistsError):
            os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_gzip_once(destination: Path, payload: bytes) -> None:
    """Atomically create one immutable gzip artifact."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    os.close(descriptor)
    try:
        with gzip.open(temporary, "wb") as handle:
            handle.write(payload)
        with suppress(FileExistsError):
            os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
