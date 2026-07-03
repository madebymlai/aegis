from __future__ import annotations

from pathlib import Path

from research.aegis_research.optimization.candidate_store_identity import (
    candidate_store_namespace,
    candidate_store_path,
)


def test_candidate_store_path_returns_expected_path() -> None:
    class _FakeConfig:
        output_dir = "/tmp/my_runs"

    path = candidate_store_path(_FakeConfig())
    assert path == Path("/tmp/my_runs/.candidate_store/candidates.sqlite3")


def test_candidate_store_namespace_returns_expected_dict() -> None:
    ns = candidate_store_namespace()
    assert ns == {
        "kind": "local_sqlite",
        "path": ".candidate_store/candidates.sqlite3",
    }
