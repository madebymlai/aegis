from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import (
    OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
    WEIGHT_BASIS,
)


def test_candidate_store_persists_completed_run_and_queries_top_candidates(tmp_path: Path) -> None:
    store_path = tmp_path / "candidate-store" / "candidates.sqlite3"
    candidates = _candidate_rows()
    leaderboard = _leaderboard(candidates, values=[0.10, 0.30, 0.20])
    provenance = {"run_id": "run-a", "artifact_schema": "strategy_run.v3"}

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            leaderboard=leaderboard,
            provenance=provenance,
        )

        top = store.top_candidates_by_run("run-a", limit=2)
        params = store.params_by_candidate_key(top[0]["candidate"]["candidate_key"], run_id="run-a")
        stored_provenance = store.provenance_by_candidate(
            top[0]["candidate"]["candidate_key"], run_id="run-a"
        )

    assert [row["leaderboard_row"]["ranking_metric_value"] for row in top] == [0.30, 0.20]
    assert params == {"fast_window": 5, "slow_window": 10}
    assert stored_provenance == provenance
    if os.name == "posix":
        assert store_path.stat().st_mode & 0o077 == 0
        assert store_path.parent.stat().st_mode & 0o077 == 0


def test_candidate_store_queries_top_candidates_by_metric_across_runs(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    run_a_candidates = _candidate_rows(data_symbol="SYN_A")
    run_b_candidates = _candidate_rows(data_symbol="SYN_B")

    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=run_a_candidates,
            leaderboard=_leaderboard(run_a_candidates, values=[0.10, 0.30, 0.20]),
            provenance={"run_id": "run-a"},
        )
        store.insert_completed_run(
            run_id="run-b",
            candidate_rows=run_b_candidates,
            leaderboard=_leaderboard(run_b_candidates, values=[0.40, 0.05, None]),
            provenance={"run_id": "run-b"},
        )

        top = store.top_candidates_by_metric("total_return", direction="desc", limit=3)

    assert [row["leaderboard_row"]["ranking_metric_value"] for row in top] == [0.40, 0.30, 0.20]
    assert [row["provenance"]["run_id"] for row in top] == ["run-b", "run-a", "run-a"]


def test_candidate_store_resolves_promotion_token_params(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    candidate = candidates[0]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            leaderboard=_leaderboard(candidates, values=[0.10, 0.30, 0.20]),
            provenance={"run_id": "run-a"},
        )
        store.insert_promotion(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=candidate["params"],
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        params = store.params_by_promotion_token("lock_run-a_strategy_demo_ma_cross_rank1")

    assert params == candidate["params"]


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


def test_candidate_store_rejects_conflicting_duplicate_candidate_payload(tmp_path: Path) -> None:
    candidates = _candidate_rows()
    changed = [dict(candidates[0], row_index=99), *candidates[1:]]

    with CandidateStore(tmp_path / "candidates.sqlite3") as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=candidates,
            leaderboard=_leaderboard(candidates, values=[0.10, 0.30, 0.20]),
            provenance={"run_id": "run-a"},
        )

        with pytest.raises(CandidateStoreError, match="different payload"):
            store.insert_completed_run(
                run_id="run-a",
                candidate_rows=changed,
                leaderboard=_leaderboard(changed, values=[0.10, 0.30, 0.20]),
                provenance={"run_id": "run-a"},
            )


def _candidate_rows(*, data_symbol: str = "SYN") -> list[dict[str, object]]:
    index = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 10), (8, 20)],
        names=["fast_window", "slow_window"],
    )
    return candidate_rows_from_param_index(
        index,
        source_identity={"source": "playbook", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": [data_symbol], "timeframe": "1D"},
        portfolio_policy={"entry_budget": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )


def _leaderboard(candidates: list[dict[str, object]], *, values: list[float | None]) -> dict[str, object]:
    rows = []
    for candidate, value in sorted(
        zip(candidates, values, strict=True),
        key=lambda item: (item[1] is None, -(item[1] or 0.0)),
    ):
        rows.append(
            {
                "candidate_key": candidate["candidate_key"],
                "params": candidate["params"],
                "ranking_metric": "total_return",
                "ranking_direction": "desc",
                "ranking_metric_value": value,
                "metrics": {"total_return": value, "sharpe_ratio": None},
                "selected_split_count": 1,
                "eligible_split_count": 1,
                "split_refs": [0],
                "weight_basis": WEIGHT_BASIS,
                "held_out_row_count": 10,
                "oos_metric_values": [] if value is None else [value],
                "oos_metric_min": value,
                "oos_metric_max": value,
            }
        )
    return {
        "schema_version": OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
        "ranking_metric": "total_return",
        "ranking_direction": "desc",
        "metric_registry_fingerprint": "fp-test",
        "weight_basis": WEIGHT_BASIS,
        "summary": {"attempted_splits": 1, "selected_splits": len(rows)},
        "rows": rows,
        "failure_samples": [],
    }
