from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import (
    OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
    WEIGHT_BASIS,
)
from research.aegis_research.optimization.promotion import (
    ComponentPromotionRef,
    PromotionResolutionError,
    resolve_component_promotion,
)


def test_resolves_lock_id_for_matching_component(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]
        params = _strategy_params(candidate)
        store.insert_promotion(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=params,
            provenance={"run_id": "run-a", "candidate_key": candidate["candidate_key"]},
        )

        resolved = resolve_component_promotion(
            ComponentPromotionRef(
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
        store.insert_promotion(
            token="lock_run-a_strategy_demo_ma_cross_rank1",
            run_id="run-a",
            component_family="strategies",
            component_id="demo.ma_cross",
            component_slot="strategy:demo.ma_cross",
            candidate_key=candidate["candidate_key"],
            params=params,
            provenance={"run_id": "run-a"},
        )

        with pytest.raises(PromotionResolutionError, match="does not belong"):
            resolve_component_promotion(
                ComponentPromotionRef(
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

        resolved = resolve_component_promotion(
            ComponentPromotionRef(
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

        with pytest.raises(PromotionResolutionError, match="does not include component"):
            resolve_component_promotion(
                ComponentPromotionRef(
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
        PromotionResolutionError, match="exactly one"
    ):
        resolve_component_promotion(
            ComponentPromotionRef(
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
        with pytest.raises(PromotionResolutionError, match="unknown promotion token"):
            resolve_component_promotion(
                ComponentPromotionRef(
                    component_family="strategies",
                    component_id="demo.ma_cross",
                    component_slot="strategy:demo.ma_cross",
                    lock_id="missing-lock",
                ),
                store=store,
            )
        with pytest.raises(PromotionResolutionError, match="unknown candidate key"):
            resolve_component_promotion(
                ComponentPromotionRef(
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
        leaderboard=_leaderboard(candidates),
        provenance={"run_id": "run-a", "source": _source_evidence()},
    )
    return store


def _candidate_rows() -> list[dict[str, object]]:
    fast_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_cross", "strategy:demo.ma_cross", "slow_window")
    index = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 10)],
        names=[fast_key, slow_key],
    )
    return candidate_rows_from_param_index(
        index,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
        portfolio_policy={"entry_budget": 1.0},
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


def _leaderboard(candidates: list[dict[str, object]]) -> dict[str, object]:
    rows = []
    for candidate, value in zip(candidates, [0.30, 0.10], strict=True):
        rows.append(
            {
                "candidate_key": candidate["candidate_key"],
                "params": candidate["params"],
                "ranking_metric": "total_return",
                "ranking_direction": "desc",
                "ranking_metric_value": value,
                "metrics": {"total_return": value},
                "selected_split_count": 1,
                "eligible_split_count": 1,
                "split_refs": [0],
                "weight_basis": WEIGHT_BASIS,
                "held_out_row_count": 10,
                "oos_metric_values": [value],
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
