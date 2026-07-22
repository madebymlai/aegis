from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest

from research.aegis_research.atomic_write import hash_file, write_json, write_new_json
from research.aegis_research.canonical_json import canonical_json_bytes


def test_write_json_bytes_identical_to_canonical_json_indented(tmp_path: Path) -> None:
    """write_json produces byte output matching canonical_json_bytes(payload, indent=2)."""
    target = tmp_path / "artifact.json"
    payload = {"b": 2, "a": 1}

    write_json(target, payload)

    assert target.read_bytes() == canonical_json_bytes(payload, indent=2)


def test_write_json_creates_parent_directories(tmp_path: Path) -> None:
    """write_json creates missing parent directories."""
    target = tmp_path / "nested" / "deep" / "payload.json"

    write_json(target, {"key": True})

    assert target.exists()
    assert json.loads(target.read_text()) == {"key": True}


def test_write_json_atomic_appearance(tmp_path: Path) -> None:
    """A failed write does not corrupt or alter an existing target file."""
    target = tmp_path / "manifest.json"
    write_json(target, {"valid": True})
    original_bytes = target.read_bytes()

    with pytest.raises(TypeError):
        write_json(target, {"invalid": {object()}})

    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("*.tmp"))


def test_write_json_chmod_restricted(tmp_path: Path) -> None:
    """Written files have mode 0600 (owner read/write only)."""
    target = tmp_path / "restricted.json"
    write_json(target, {"secret": "value"})

    group_other_bits = target.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO)
    assert group_other_bits == 0, f"expected no group/other permissions, got {group_other_bits:#o}"


def test_write_new_json_claims_path_without_replacing_existing_bytes(tmp_path: Path) -> None:
    target = tmp_path / "run.json"
    write_new_json(target, {"owner": "first"})

    with pytest.raises(FileExistsError):
        write_new_json(target, {"owner": "second"})

    assert json.loads(target.read_text()) == {"owner": "first"}
    assert not list(tmp_path.glob("*.tmp"))


def test_hash_file_is_sha256_hexdigest(tmp_path: Path) -> None:
    """hash_file returns the correct sha256 hex digest."""
    payload = tmp_path / "payload.txt"
    content = b"hello sha256\n"
    payload.write_bytes(content)

    digest = hash_file(payload)
    expected = hashlib.sha256(content).hexdigest()

    assert digest == expected
    assert len(digest) == 64


def test_hash_file_empty_file(tmp_path: Path) -> None:
    """hash_file handles an empty file correctly."""
    empty = tmp_path / "empty"
    empty.write_bytes(b"")

    digest = hash_file(empty)
    expected = hashlib.sha256(b"").hexdigest()

    assert digest == expected


def test_hash_file_large_file(tmp_path: Path) -> None:
    """hash_file correctly digests a file larger than the 1MB chunk size."""
    large = tmp_path / "large.bin"
    content = b"x" * (3 * 1024 * 1024)  # 3 MB
    large.write_bytes(content)

    digest = hash_file(large)
    expected = hashlib.sha256(content).hexdigest()

    assert digest == expected


def test_hash_file_deterministic(tmp_path: Path) -> None:
    """hash_file returns the same digest on repeated calls."""
    target = tmp_path / "stable.txt"
    target.write_text("deterministic\n")

    first = hash_file(target)
    second = hash_file(target)

    assert first == second
