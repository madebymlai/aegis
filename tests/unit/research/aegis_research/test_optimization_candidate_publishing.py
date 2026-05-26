from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from research.aegis_research.optimization.candidate_publishing import (
    activate_candidate_run,
    build_candidate_store_provenance,
    candidate_store_namespace,
    candidate_store_path,
    publish_candidates,
)
from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_ACTIVE,
    PUBLICATION_PENDING,
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import (
    OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
    WEIGHT_BASIS,
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


def test_build_candidate_store_provenance_returns_expected_keys() -> None:
    class _FakeRecorder:
        class manifest:
            run_id = "run-1"

    class _FakeDataResult:
        class quality:
            state = "ok"

        metadata = {
            "source": "synthetic",
            "symbols": ["SYN"],
            "loaded_arrays": ["Close", "Open"],
        }

    class _FakeArrayContract:
        def metadata(self) -> dict[str, Any]:
            return {"strategy_consumed_runner_data": True}

    class _FakePortfolio:
        target_exposure_cap = 1.0

    class _FakeRanking:
        metric = "total_return"
        direction = "desc"
        secondary_metrics: tuple[str, ...] = ()

    class _FakeConfig:
        portfolio = _FakePortfolio()
        ranking = _FakeRanking()

    provenance = build_candidate_store_provenance(
        _FakeRecorder(),
        optimization_source={"source": "component"},
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        config=_FakeConfig(),
        metric_registry_fingerprint="fp-abc",
    )

    assert provenance["schema_version"] == "candidate_store_provenance.v1"
    assert provenance["run_id"] == "run-1"
    assert provenance["strategy_artifact_id"] == "strategy.run"
    assert provenance["source"] == {"source": "component"}
    assert provenance["portfolio"] == {"target_exposure_cap": 1.0}
    assert provenance["ranking"]["metric"] == "total_return"
    assert provenance["ranking"]["direction"] == "desc"
    assert provenance["metric_registry_fingerprint"] == "fp-abc"


def test_publish_candidates_inserts_run_and_locks(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    candidates = _candidate_rows()
    leaderboard = _leaderboard(candidates, values=[0.30, 0.10])
    provenance = {"run_id": "run-a"}
    lock_records = [
        {
            "token": "lock_run-a_strategy",
            "run_id": "run-a",
            "component_family": "strategies",
            "component_id": "demo.ma_cross",
            "component_slot": "strategy:demo.ma_cross",
            "candidate_key": candidates[0]["candidate_key"],
            "params": candidates[0]["params"],
            "provenance": {"run_id": "run-a"},
        },
    ]

    publish_candidates(
        store_path,
        run_id="run-a",
        candidate_rows=candidates,
        leaderboard=leaderboard,
        provenance=provenance,
        lock_records=lock_records,
    )

    with CandidateStore(store_path) as store:
        top = store.top_candidates_by_run("run-a", limit=2)
        lock = store.lock_by_token("lock_run-a_strategy")

    assert len(top) == 2
    assert top[0]["candidate"]["candidate_key"] == candidates[0]["candidate_key"]
    assert top[0]["publication_state"] == PUBLICATION_PENDING
    assert lock["token"] == "lock_run-a_strategy"
    assert lock["publication_state"] == PUBLICATION_PENDING


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


def test_activate_candidate_run_sets_active_state(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"
    candidates = _candidate_rows()
    leaderboard = _leaderboard(candidates, values=[0.30])
    provenance = {"run_id": "run-a"}

    publish_candidates(
        store_path,
        run_id="run-a",
        candidate_rows=candidates,
        leaderboard=leaderboard,
        provenance=provenance,
        lock_records=[],
        publication_state=PUBLICATION_PENDING,
    )

    activate_candidate_run(store_path, "run-a")

    with CandidateStore(store_path) as store:
        top = store.top_candidates_by_run("run-a", limit=1)

    assert top[0]["publication_state"] == PUBLICATION_ACTIVE


def test_activate_candidate_run_raises_for_unknown_run(tmp_path: Path) -> None:
    store_path = tmp_path / "candidates.sqlite3"

    with pytest.raises(CandidateStoreError, match="candidate_store_activation_failed"):
        activate_candidate_run(store_path, "nonexistent-run")


def _candidate_rows(data_symbol: str = "SYN") -> list[dict[str, Any]]:
    fast_key = component_param_key(
        "strategies", "demo.ma_cross", "strategy:demo.ma_cross", "fast_window"
    )
    slow_key = component_param_key(
        "strategies", "demo.ma_cross", "strategy:demo.ma_cross", "slow_window"
    )
    index = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 10)],
        names=[fast_key, slow_key],
    )
    return candidate_rows_from_param_index(
        index,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={
            "source": "synthetic",
            "symbols": [data_symbol],
            "timeframe": "1D",
        },
        portfolio_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )


def _leaderboard(candidates: list[dict[str, Any]], values: list[float | None]) -> dict[str, Any]:
    rows = []
    for candidate, value in zip(candidates, values, strict=True):
        rows.append(
            {
                "candidate_key": candidate["candidate_key"],
                "params": candidate["params"],
                "ranking_metric": "total_return",
                "ranking_direction": "desc",
                "ranking_metric_value": value,
                "metrics": {"total_return": value} if value is not None else {},
                "selected_split_count": 1,
                "eligible_split_count": 1,
                "split_refs": [0],
                "weight_basis": WEIGHT_BASIS,
                "held_out_row_count": 10,
                "oos_metric_values": [value] if value is not None else [],
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
