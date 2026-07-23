from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.candidates.models import CandidateSet
from research.aegis_research.candidates.records import candidate_rows_from_result
from research.aegis_research.candidates.store import (
    SCHEMA_VERSION,
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.run.identity import RunId
from tests.support.research.aegis_research.factories import make_selection_identity


def _data_identity(instrument_id: str = "SYN.XNAS") -> dict[str, object]:
    return {
        "schema_version": "candidate_data_identity.v3",
        "requested_instrument_ids": [instrument_id],
        "instrument_ids": [instrument_id],
        "timeframe": "1D",
    }


def _provenance(run_id: str = "run-a") -> dict[str, object]:
    return {
        "schema_version": "candidate_store_provenance.v3",
        "run_id": run_id,
        "selection_identity": make_selection_identity(),
    }


def _candidate_set(
    candidates: list[dict[str, Any]],
    *,
    run_id: str = "run-a",
    provenance: dict[str, object] | None = None,
) -> CandidateSet:
    return CandidateSet.create(
        run_id=RunId(run_id),
        candidates=candidates,
        provenance=provenance or _provenance(run_id),
    )


def test_candidate_store_persists_three_candidates_and_queries_by_run(tmp_path: Path) -> None:
    store_path = tmp_path / "candidate-store" / "candidates.sqlite3"
    candidates = _candidate_rows(values=(0.30, 0.20, 0.10))
    provenance = _provenance()

    with CandidateStore(store_path) as store:
        store.commit_candidates(_candidate_set(candidates, provenance=provenance))

        resolved = {
            role: store.candidate_key_for_role("run-a", role)
            for role in ("best", "median", "worst")
        }
        stored = store.candidate_by_key(resolved["best"], run_id="run-a")

    assert resolved == {row["role"]: row["candidate_key"] for row in candidates}
    assert stored["params"] == {"fast_window": 5, "slow_window": 10}
    assert stored["candidate"]["complete_period_metrics"]["total_return"] == 0.30
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
        store.commit_candidates(_candidate_set(candidates))
        by_role = {row["role"]: row["candidate_key"] for row in candidates}

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
        data_identity=_data_identity(),
        selection_identity=make_selection_identity(),
    )

    with CandidateStore(store_path) as store:
        store.commit_candidates(_candidate_set(candidates))

        distinct_keys = {
            store.candidate_key_for_role("run-a", role) for role in ("best", "median", "worst")
        }
        connection = store._connection
        candidate_count = connection.execute(
            "SELECT COUNT(*) FROM candidates WHERE run_id = ?", ("run-a",)
        ).fetchone()[0]
        ranking_count = connection.execute(
            "SELECT COUNT(*) FROM candidate_rankings WHERE run_id = ?", ("run-a",)
        ).fetchone()[0]

    # One deployable candidate fills all three slots: one stored candidate, three roles.
    assert len(distinct_keys) == 1
    assert candidate_count == 1
    assert ranking_count == 3


def test_candidate_store_commit_is_the_visibility_boundary(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(store_path) as store:
        store.commit_candidates(_candidate_set(candidates))

        assert store.candidate_key_for_role("run-a", "best") == candidate["candidate_key"]
        assert (
            store.candidate_by_key(candidate["candidate_key"], run_id="run-a")["params"]
            == candidate["params"]
        )


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
        data_identity=_data_identity(),
        selection_identity=make_selection_identity(),
    )

    with CandidateStore(store_path) as store:
        store.commit_candidates(_candidate_set(candidates))

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
    # Forward-first: a store from the previous (denormalised rankings) schema fails the
    # version check and must be recreated — there is no migration path.
    store_path = tmp_path / "candidates.sqlite3"
    connection = sqlite3.connect(store_path)
    connection.execute(
        "CREATE TABLE candidate_store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO candidate_store_meta (key, value) VALUES ('schema_version', '6')"
    )
    connection.commit()
    connection.close()
    if os.name == "posix":
        store_path.chmod(0o600)

    assert SCHEMA_VERSION == 8
    with pytest.raises(CandidateStoreError, match="schema version 6"):
        CandidateStore(store_path)


def test_candidate_store_rejects_conflicting_duplicate_candidate_payload(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    # Same candidate_key (identity unchanged) but a different evidence payload.
    changed = [dict(candidates[0], mean_rank=99.0), *candidates[1:]]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.commit_candidates(_candidate_set(candidates))

        with pytest.raises(CandidateStoreError, match="different committed Candidate Set"):
            store.commit_candidates(_candidate_set(changed))


def test_candidate_store_raises_on_empty_candidate_rows(tmp_path: Path) -> None:
    with (
        CandidateStore(tmp_path / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="no candidate rows"),
    ):
        store.commit_candidates(
            CandidateSet.create(
                run_id=RunId("run-a"), candidates=[], provenance={"run_id": "run-a"}
            )
        )


def test_candidate_store_exact_recommit_is_idempotent(tmp_path: Path) -> None:
    candidate_set = _candidate_set(_candidate_rows())

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.commit_candidates(candidate_set)
        store.commit_candidates(candidate_set)

        assert (
            store.candidate_key_for_role("run-a", "best")
            == candidate_set.candidates[0]["candidate_key"]
        )


def test_candidate_store_rejects_incomplete_representative_set(tmp_path: Path) -> None:
    candidates = _candidate_rows()[:2]

    with (
        CandidateStore(tmp_path / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="exactly three representative roles"),
    ):
        store.commit_candidates(_candidate_set(candidates))


def test_candidate_store_rejects_duplicate_representative_role(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    duplicated = [candidates[0], dict(candidates[1], role="best"), candidates[2]]

    with (
        CandidateStore(tmp_path / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="unique best, median, and worst"),
    ):
        store.commit_candidates(_candidate_set(duplicated))


def test_candidate_store_rejects_provenance_for_another_run(tmp_path: Path) -> None:
    candidate_set = _candidate_set(
        _candidate_rows(),
        provenance=_provenance("another-run"),
    )

    with (
        CandidateStore(tmp_path / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="provenance run_id"),
    ):
        store.commit_candidates(candidate_set)


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
        observation_block_metrics={"block-000": {"total_return": total_return}},
        metrics={"total_return": total_return},
    )


def _candidate_rows(
    *,
    data_instrument_id: str = "SYN.XNAS",
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
        data_identity=_data_identity(data_instrument_id),
        selection_identity=make_selection_identity(),
        book_settings={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
