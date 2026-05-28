from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.optimization.candidate_publishing import (
    activate_candidate_run,
    candidate_store_namespace,
    candidate_store_path,
    publish_candidates,
)
from research.aegis_research.optimization.candidate_store import (
    CandidateStoreError,
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


def test_publish_candidates_raises_on_empty_candidate_rows(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"

    with pytest.raises(CandidateStoreError, match="no candidate rows"):
        publish_candidates(
            store_path,
            run_id="run-a",
            candidate_rows=[],
            leaderboard={"rows": []},
            provenance={"run_id": "run-a"},
            lock_records=[],
        )


def test_activate_candidate_run_raises_for_unknown_run(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"

    with pytest.raises(CandidateStoreError, match="candidate_store_activation_failed"):
        activate_candidate_run(store_path, "nonexistent-run")
