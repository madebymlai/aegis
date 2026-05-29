from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.optimization.evidence import candidate_rows_from_result
from research.aegis_research.optimization.lock_resolution import (
    ComponentLockRef,
    LockResolutionError,
    resolve_component_lock,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)


def test_resolves_lock_id_for_matching_component(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]
        params = _strategy_params(candidate)
        store.insert_lock(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=params,
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        resolved = resolve_component_lock(
            ComponentLockRef(
                component_family="strategies",
                component_id="demo.ma_cross",
                component_slot="strategy:demo.ma_cross",
                lock_id="lock_run-a_strategy_demo_ma_cross_rank1",
            ),
            store=store,
        )

    assert resolved.reference_kind == "lock_id"
    assert resolved.candidate_key == candidate["candidate_key"]
    assert resolved.params == params
    assert resolved.provenance["run_id"] == "run-a"


def test_rejects_lock_id_for_wrong_component(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]
        params = _strategy_params(candidate)
        store.insert_lock(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=params,
            provenance={"run_id": "run-a"},
        )

        with pytest.raises(LockResolutionError, match="does not belong"):
            resolve_component_lock(
                ComponentLockRef(
                    component_family="strategies",
                    component_id="demo.other",
                    component_slot="strategy:demo.other",
                    lock_id="lock_run-a_strategy_demo_ma_cross_rank1",
                ),
                store=store,
            )


def test_resolves_direct_candidate_id_pin(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]

        resolved = resolve_component_lock(
            ComponentLockRef(
                component_family="strategies",
                component_id="demo.ma_cross",
                component_slot="strategy:demo.ma_cross",
                candidate_id=candidate["candidate_key"],
                run_id="run-a",
            ),
            store=store,
        )

    assert resolved.reference_kind == "candidate_id"
    assert resolved.candidate_key == candidate["candidate_key"]
    assert resolved.params == _strategy_params(candidate)
    assert resolved.provenance["component_id"] == "demo.ma_cross"


def test_rejects_direct_candidate_id_for_wrong_component(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]

        with pytest.raises(LockResolutionError, match="does not include component"):
            resolve_component_lock(
                ComponentLockRef(
                    component_family="strategies",
                    component_id="demo.other",
                    component_slot="strategy:demo.other",
                    candidate_id=candidate["candidate_key"],
                    run_id="run-a",
                ),
                store=store,
            )


def test_rejects_ambiguous_reference_fields(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store, pytest.raises(
        LockResolutionError, match="exactly one"
    ):
        resolve_component_lock(
            ComponentLockRef(
                component_family="strategies",
                component_id="demo.ma_cross",
                component_slot="strategy:demo.ma_cross",
                lock_id="lock-id",
                candidate_id="cand_key",
            ),
            store=store,
        )


def test_rejects_missing_lock_or_candidate(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        with pytest.raises(LockResolutionError, match="unknown lock token"):
            resolve_component_lock(
                ComponentLockRef(
                    component_family="strategies",
                    component_id="demo.ma_cross",
                    component_slot="strategy:demo.ma_cross",
                    lock_id="missing-lock",
                ),
                store=store,
            )
        with pytest.raises(LockResolutionError, match="unknown candidate key"):
            resolve_component_lock(
                ComponentLockRef(
                    component_family="strategies",
                    component_id="demo.ma_cross",
                    component_slot="strategy:demo.ma_cross",
                    candidate_id="cand_missing",
                    run_id="run-a",
                ),
                store=store,
            )


def _store_with_candidate(tmp_path: Path) -> CandidateStore:
    store = CandidateStore(tmp_path / "candidates.sqlite3")
    candidates = _candidate_rows()
    store.insert_completed_run(
        run_id="run-a",
        candidate_rows=candidates,
        ranking_metric="total_return",
        provenance={"run_id": "run-a", "source": _source_evidence()},
    )
    return store


def _candidate(params: dict[str, object], score: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params=params,
        score=score,
        selection_metrics={0: {"total_return": score}},
        metrics={"total_return": score},
        held_out_metrics={0: {"total_return": score}},
    )


def _candidate_rows() -> list[dict[str, object]]:
    fast_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "slow_window")
    winner = _candidate({fast_key: 2, slow_key: 10}, 0.30)
    runner_up = _candidate({fast_key: 5, slow_key: 10}, 0.10)
    result = OptimizationResult(best=winner, median=runner_up, worst=runner_up)
    return candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
        portfolio_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )


def _strategy_params(candidate: dict[str, object]) -> dict[str, object]:
    fast_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "slow_window")
    params = candidate["params"]
    assert isinstance(params, dict)
    return {"fast_window": params[fast_key], "slow_window": params[slow_key]}


def _source_evidence() -> dict[str, object]:
    return {
        "schema_version": "component_optimization_source.v1",
        "source": "component",
        "strategy": {
            "family": "strategies",
            "slot": "strategy:demo.ma_cross",
            "id": "demo.ma_cross",
            "version": "1.0.0",
            "fixed_params": {},
            "param_keys": {
                "fast_window": component_param_key(
                    "strategies", "demo.ma_cross", "strategy:demo.ma_cross", "fast_window"
                ),
                "slow_window": component_param_key(
                    "strategies", "demo.ma_cross", "strategy:demo.ma_cross", "slow_window"
                ),
            },
        },
        "indicators": [],
    }
