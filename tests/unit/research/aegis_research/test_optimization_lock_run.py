"""Unit tests for the top-level Lock run-resolution deep module.

A ``Lock`` (``run_id`` + ``candidate_id`` = the ``candidates`` primary key) reproduces
one prior Candidate end-to-end: the deep module loads that Candidate by its primary key
and fans its parameters across every Component using the component-param slicing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.config import Lock
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.optimization.evidence import candidate_rows_from_result
from research.aegis_research.optimization.lock_run import (
    LockRunResolutionError,
    resolve_lock_run,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)


def test_resolves_per_component_params_for_locked_candidate(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]

        resolved = resolve_lock_run(
            Lock(run_id="run-a", candidate_id=candidate["candidate_key"]),
            store=store,
        )

    assert resolved.run_id == "run-a"
    assert resolved.candidate_key == candidate["candidate_key"]
    # Params fan across both the strategy and the indicator slots.
    strategy_key = ("strategies", "demo.ma_cross", "strategy:demo.ma_cross")
    indicator_key = ("indicators", "demo.mom", "demo.mom")
    assert resolved.component_params[strategy_key] == {"fast_window": 2, "slow_window": 10}
    assert resolved.component_params[indicator_key] == {"window": 20}


def test_rejects_unknown_run_id(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]
        with pytest.raises(LockRunResolutionError, match="unknown candidate"):
            resolve_lock_run(
                Lock(run_id="run-missing", candidate_id=candidate["candidate_key"]),
                store=store,
            )


def test_rejects_unknown_candidate_id(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:  # noqa: SIM117
        with pytest.raises(LockRunResolutionError, match="unknown candidate"):
            resolve_lock_run(
                Lock(run_id="run-a", candidate_id="cand_missing"),
                store=store,
            )


def test_rejects_candidate_missing_referenced_component(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path, drop_indicator_runtime=True) as store:
        candidate = store.top_candidates_by_run("run-a", limit=1)[0]["candidate"]
        with pytest.raises(LockRunResolutionError, match="does not include component"):
            resolve_lock_run(
                Lock(run_id="run-a", candidate_id=candidate["candidate_key"]),
                store=store,
            )


def _store_with_candidate(tmp_path: Path, *, drop_indicator_runtime: bool = False) -> CandidateStore:
    store = CandidateStore(tmp_path / "candidates.sqlite3")
    candidates = _candidate_rows()
    store.insert_completed_run(
        run_id="run-a",
        candidate_rows=candidates,
        ranking_metric="total_return",
        provenance={
            "run_id": "run-a",
            "source": _source_evidence(drop_indicator_runtime=drop_indicator_runtime),
        },
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
    window_key = component_param_key("indicators", "demo.mom", "demo.mom", "window")
    winner = _candidate({fast_key: 2, slow_key: 10, window_key: 20}, 0.30)
    result = OptimizationResult(best=winner, median=winner, worst=winner)
    return candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
        portfolio_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )


def _source_evidence(*, drop_indicator_runtime: bool = False) -> dict[str, object]:
    indicators: list[dict[str, object]] = []
    if not drop_indicator_runtime:
        indicators.append(
            {
                "family": "indicators",
                "slot": "demo.mom",
                "id": "demo.mom",
                "version": "1.0.0",
                "fixed_params": {},
                "param_keys": {
                    "window": component_param_key("indicators", "demo.mom", "demo.mom", "window"),
                },
            }
        )
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
        "indicators": indicators,
    }
