from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

import research.aegis_research.optimization.candidate_store as candidate_store_module
import research.aegis_research.optimization.canonical_json as canonical_json_module
from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_PENDING,
    SCHEMA_VERSION,
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_result
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
        params = store.params_by_candidate_key(top[0]["candidate"]["candidate_key"], run_id="run-a")
        stored_provenance = store.provenance_by_candidate(
            top[0]["candidate"]["candidate_key"], run_id="run-a"
        )

    assert [row["role"] for row in top] == ["best", "median", "worst"]
    assert [row["rank"] for row in top] == [1, 2, 3]
    assert [row["ranking_metric_value"] for row in top] == [0.30, 0.20, 0.10]
    assert params == {"fast_window": 5, "slow_window": 10}
    assert stored_provenance == provenance
    if os.name == "posix":
        assert store_path.stat().st_mode & 0o077 == 0
        assert store_path.parent.stat().st_mode & 0o077 == 0


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
        store.insert_lock(
            token="lock_pending",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=candidate["params"],
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
            publication_state=PUBLICATION_PENDING,
        )

        assert store.top_candidates_by_run("run-a", limit=1) == []
        with pytest.raises(CandidateStoreError, match="unknown candidate key"):
            store.params_by_candidate_key(candidate["candidate_key"], run_id="run-a")
        with pytest.raises(CandidateStoreError, match="unknown lock token"):
            store.params_by_lock_token("lock_pending")

        store.activate_run("run-a")

        assert store.top_candidates_by_run("run-a", limit=1)
        assert store.params_by_lock_token("lock_pending") == candidate["params"]


def test_candidate_store_active_lock_requires_active_candidate(tmp_path: Path) -> None:
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
        store.insert_lock(
            token="lock_active_lock_pending_candidate",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=candidate["params"],
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        with pytest.raises(CandidateStoreError, match="unknown lock token"):
            store.params_by_lock_token("lock_active_lock_pending_candidate")

        store.activate_run("run-a")

        assert (
            store.params_by_lock_token("lock_active_lock_pending_candidate")
            == candidate["params"]
        )


def test_candidate_store_resolves_lock_token_params(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )
        store.insert_lock(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=candidate["params"],
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        params = store.params_by_lock_token("lock_run-a_strategy_demo_ma_cross_rank1")

    assert params == candidate["params"]


def test_candidate_store_json_columns_use_canonical_json_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def canonical_json_bytes(value: object) -> bytes:
        calls.append(value)
        return b'{"serialized":"through-canonical-json"}'

    monkeypatch.setattr(canonical_json_module, "canonical_json_bytes", canonical_json_bytes)

    payload = {"z": 1, "a": 2}

    assert candidate_store_module._json_dumps(payload) == '{"serialized":"through-canonical-json"}'
    assert calls == [payload]


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
    # Forward-first: a store from the previous (leaderboard) schema fails the version
    # check and must be recreated — there is no migration path.
    store_path = tmp_path / "candidates.sqlite3"
    connection = sqlite3.connect(store_path)
    connection.execute(
        "CREATE TABLE candidate_store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO candidate_store_meta (key, value) VALUES ('schema_version', '3')"
    )
    connection.commit()
    connection.close()
    if os.name == "posix":
        store_path.chmod(0o600)

    assert SCHEMA_VERSION == 4
    with pytest.raises(CandidateStoreError, match="schema version 3"):
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


def test_candidate_store_reinserting_same_lock_token_is_idempotent(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )
        for _ in range(2):
            store.insert_lock(
                token="lock_duplicate",
                run_id="run-a",
                component_family="strategies",
                component_id="demo.ma_cross",
                component_slot="strategy:demo.ma_cross",
                candidate_key=candidate["candidate_key"],
                params=candidate["params"],
                provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
            )

        assert store.params_by_lock_token("lock_duplicate") == candidate["params"]


def test_candidate_store_rejects_conflicting_duplicate_lock_payload(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            ranking_metric="total_return",
            provenance={"run_id": "run-a"},
        )
        store.insert_lock(
            token="lock_conflict",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=candidate["params"],
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        with pytest.raises(CandidateStoreError, match="different payload"):
            store.insert_lock(
                token="lock_conflict",
                run_id="run-a",
                component_family="strategies",
                component_id="demo.ma_cross",
                component_slot="strategy:demo.ma_cross",
                candidate_key=candidate["candidate_key"],
                params={"fast_window": 99},
                provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
            )


def test_candidate_store_raises_on_empty_candidate_rows(tmp_path: Path) -> None:
    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        with pytest.raises(CandidateStoreError, match="no candidate rows"):
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


def _candidate(params: dict[str, object], score: float, *, total_return: float) -> EvaluatedCandidate:
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
) -> list[dict[str, object]]:
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
        portfolio_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
