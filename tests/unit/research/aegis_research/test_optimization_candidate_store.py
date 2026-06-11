from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.optimization.candidate_evidence import candidate_rows_from_result
from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_PENDING,
    SCHEMA_VERSION,
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)


def test_candidate_store_persists_three_candidates_and_queries_by_run(tmp_path: Path) -> None:
    store_path = tmp_path / "candidate-store" / "candidates.sqlite3"
    candidates = _candidate_rows(values=(0.30, 0.20, 0.10))
    provenance = {"run_id": "run-a", "artifact_schema": "optimization_artifact.v1"}

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance=provenance,
        )

        top = store.top_candidates_by_run("run-a")
        stored = store.candidate_by_key(top[0]["candidate"]["candidate_key"], run_id="run-a")

    assert [row["role"] for row in top] == ["best", "median", "worst"]
    assert [row["rank"] for row in top] == [1, 2, 3]
    assert [row["ranking_metric_value"] for row in top] == [0.30, 0.20, 0.10]
    assert stored["params"] == {"fast_window": 5, "slow_window": 10}
    assert stored["provenance"] == provenance
    if os.name == "posix":
        assert store_path.stat().st_mode & 0o077 == 0
        assert store_path.parent.stat().st_mode & 0o077 == 0


def test_candidate_key_for_role_resolves_each_representative(tmp_path: Path) -> None:
    # aegis-rd-6ie: roles are the storage-free handle — (run_id, role) maps to the same
    # candidate_key the ranked table exposes; an unknown role raises.
    store_path = tmp_path / "candidates.sqlite3"
    candidates = _candidate_rows(values=(0.30, 0.20, 0.10))

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )
        by_role = {
            row["role"]: row["candidate"]["candidate_key"]
            for row in store.top_candidates_by_run("run-a")
        }

        for role in ("best", "median", "worst"):
            assert store.candidate_key_for_role("run-a", role) == by_role[role]
        with pytest.raises(CandidateStoreError, match="unknown role"):
            store.candidate_key_for_role("run-a", "nonesuch")


def test_candidate_store_deduplicates_single_candidate_into_three_roles(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    only = _candidate({"fast_window": 7, "slow_window": 14}, 0.5, total_return=0.5)
    candidates = candidate_rows_from_result(
        OptimizationResult(best=only, median=only, worst=only),
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
    )

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )

        top = store.top_candidates_by_run("run-a")
        distinct_keys = {row["candidate"]["candidate_key"] for row in top}
        connection = store._connection
        candidate_count = connection.execute(
            "SELECT COUNT(*) FROM candidates WHERE run_id = ?", ("run-a",)
        ).fetchone()[0]
        ranking_count = connection.execute(
            "SELECT COUNT(*) FROM candidate_rankings WHERE run_id = ?", ("run-a",)
        ).fetchone()[0]

    # One deployable candidate fills all three slots: one stored candidate, three roles.
    assert [row["role"] for row in top] == ["best", "median", "worst"]
    assert len(distinct_keys) == 1
    assert candidate_count == 1
    assert ranking_count == 3


def test_candidate_store_pending_run_is_not_queryable_until_activation(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
            publication_state=PUBLICATION_PENDING,
        )

        assert store.top_candidates_by_run("run-a", limit=1) == []
        with pytest.raises(CandidateStoreError, match="unknown candidate key"):
            store.candidate_by_key(candidate["candidate_key"], run_id="run-a")

        store.activate_run("run-a")

        assert store.top_candidates_by_run("run-a", limit=1)
        assert store.candidate_by_key(
            candidate["candidate_key"], run_id="run-a"
        )["params"] == candidate["params"]


def test_candidate_store_has_no_per_component_lock_surface(tmp_path: Path) -> None:
    # ADR-0006 teardown: the per-Component lock model is gone. A Lock is now the
    # transparent top-level (run_id, candidate_id) — no lock table, no lock methods.
    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        for removed in ("insert_lock", "lock_by_token", "params_by_lock_token"):
            assert not hasattr(store, removed)
        tables = {
            row[0]
            for row in store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "candidate_locks" not in tables


def test_candidate_store_persists_json_columns_in_canonical_form(tmp_path: Path) -> None:
    # The durable bytes are the contract: Canonical Form (sorted keys, compact
    # separators) keeps stored candidate rows hash-stable across processes, so the
    # raw column must not depend on the insertion order of the params mapping.
    store_path = tmp_path / "candidates.sqlite3"
    scrambled_params = {"slow_window": 10, "fast_window": 5}
    only = _candidate(scrambled_params, 0.5, total_return=0.5)
    candidates = candidate_rows_from_result(
        OptimizationResult(best=only, median=only, worst=only),
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
    )

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )

    connection = sqlite3.connect(store_path)
    try:
        rows = connection.execute(
            "SELECT DISTINCT params_json FROM candidates WHERE run_id = 'run-a'"
        ).fetchall()
    finally:
        connection.close()

    assert rows == [('{"fast_window":5,"slow_window":10}',)]


def test_candidate_store_rejects_incompatible_schema_version(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    connection = sqlite3.connect(store_path)
    connection.execute(
        "CREATE TABLE candidate_store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO candidate_store_meta (key, value) VALUES ('schema_version', '999')"
    )
    connection.commit()
    connection.close()
    if os.name == "posix":
        store_path.chmod(0o600)

    with pytest.raises(CandidateStoreError, match="schema version 999"):
        CandidateStore(store_path)


def test_candidate_store_rejects_superseded_schema_version(tmp_path: Path) -> None:
    # Forward-first: a store from the previous (per-Component lock) schema fails the
    # version check and must be recreated — there is no migration path.
    store_path = tmp_path / "candidates.sqlite3"
    connection = sqlite3.connect(store_path)
    connection.execute(
        "CREATE TABLE candidate_store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO candidate_store_meta (key, value) VALUES ('schema_version', '4')"
    )
    connection.commit()
    connection.close()
    if os.name == "posix":
        store_path.chmod(0o600)

    assert SCHEMA_VERSION == 5
    with pytest.raises(CandidateStoreError, match="schema version 4"):
        CandidateStore(store_path)


def test_candidate_store_rejects_conflicting_duplicate_candidate_payload(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    # Same candidate_key (identity unchanged) but a different evidence payload.
    changed = [dict(candidates[0], score=99.0), *candidates[1:]]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )

        with pytest.raises(CandidateStoreError, match="different payload"):
            store.insert_completed_run(
                run_id="run-a",
                candidate_rows=changed,
                ranking_metric="total_return",
                provenance={"run_id": "run-a"},
            )


def test_candidate_store_raises_on_empty_candidate_rows(tmp_path: Path) -> None:
    with (
        CandidateStore(tmp_path / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="no candidate rows"),
    ):
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=[],
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )


def test_candidate_store_rejects_group_or_other_readable_directory(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions only")
    store_dir = tmp_path / "candidate-store"
    store_dir.mkdir()
    store_dir.chmod(0o755)

    with pytest.raises(CandidateStoreError, match="directory"):
        CandidateStore(store_dir / "candidates.sqlite3")


def test_candidate_store_rejects_group_or_other_readable_sqlite_file(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions only")
    store_dir = tmp_path / "candidate-store"
    store_dir.mkdir(mode=0o700)
    store_dir.chmod(0o700)
    store_path = store_dir / "candidates.sqlite3"
    store_path.touch()
    store_path.chmod(0o644)

    with pytest.raises(CandidateStoreError, match="candidate store"):
        CandidateStore(store_path)


def _candidate(params: dict[str, Any], score: float, *, total_return: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params=params,
        score=score,
        selection_metrics={0: {"total_return": total_return}},
        metrics={"total_return": total_return},
        held_out_metrics={0: {"total_return": total_return}},
    )


def _candidate_rows(
    *,
    data_symbol: str = "SYN",
    values: tuple[float, float, float] = (0.30, 0.20, 0.10),
) -> list[dict[str, Any]]:
    best, median, worst = values
    result = OptimizationResult(
        best=_candidate({"fast_window": 5, "slow_window": 10}, best, total_return=best),
        median=_candidate({"fast_window": 2, "slow_window": 10}, median, total_return=median),
        worst=_candidate({"fast_window": 8, "slow_window": 20}, worst, total_return=worst),
    )
    return candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": [data_symbol], "timeframe": "1D"},
        allocation_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
