"""Unit tests for the pipeline publishing stage (three-candidate output)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.optimization.pipeline.publishing import run_pipeline_publishing
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


class _FakeArrayContract:
    def metadata(self) -> dict[str, Any]:
        return {"schema_version": "data_array_contract.v1"}


class _FakeDataResult:
    metadata = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "timeframe": "1D",
        "loaded_arrays": ["Close", "Open"],
        "shape": (120, 1),
        "index_start": "2020-01-01",
        "index_end": "2020-06-01",
    }


class _FakeRecorder:
    def __init__(self, run_id: str) -> None:
        self.manifest = _FakeManifest(run_id)


class _FakeManifest:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.evidence: dict[str, Any] = {}


_FAMILY = "strategies"
_COMPONENT_ID = "demo.ma_cross"
_SLOT = "strategy:demo.ma_cross"
_FAST_KEY = component_param_key(_FAMILY, _COMPONENT_ID, _SLOT, "fast_window")
_SLOW_KEY = component_param_key(_FAMILY, _COMPONENT_ID, _SLOT, "slow_window")


class _FakeSource:
    evidence = {
        "schema_version": "component_optimization_source.v1",
        "source": "component",
        "strategy": {
            "family": _FAMILY,
            "id": _COMPONENT_ID,
            "slot": _SLOT,
            "version": "1.0.0",
            "fixed_params": {},
            "param_keys": {"fast_window": _FAST_KEY, "slow_window": _SLOW_KEY},
        },
        "indicators": [],
    }


def _candidate(fast: int, slow: int, score: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params={_FAST_KEY: fast, _SLOW_KEY: slow},
        score=score,
        selection_metrics={0: {"total_return": score}},
        metrics={"total_return": score},
        held_out_metrics={0: {"total_return": score - 0.01}},
    )


def _result() -> OptimizationResult:
    return OptimizationResult(
        best=_candidate(5, 10, 0.30),
        median=_candidate(2, 10, 0.20),
        worst=_candidate(8, 20, 0.10),
    )


def test_publishing_writes_three_candidate_output_to_manifest(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path).config
    recorder = _FakeRecorder("run-pub")
    store_path = tmp_path / "candidates.sqlite3"
    optimization_evidence: dict[str, Any] = {"schema_version": "optimization_route.v1"}

    out = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        optimization_source=_FakeSource(),
        optimization_result=_result(),
        portfolio_builtin={"fees": 0.001},
        optimization_evidence=optimization_evidence,
        store_path=store_path,
        metric_registry_fingerprint="fp-test",
    )

    candidate_rows = out["candidate_rows"]
    assert [row["role"] for row in candidate_rows] == ["best", "median", "worst"]
    assert [row["rank"] for row in candidate_rows] == [1, 2, 3]

    manifest_optimization = recorder.manifest.evidence["optimization"]
    assert manifest_optimization is optimization_evidence
    assert [row["role"] for row in manifest_optimization["candidates"]] == [
        "best",
        "median",
        "worst",
    ]
    assert manifest_optimization["candidate_count"] == 3


def test_publishing_persists_three_candidates_to_store(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path).config
    recorder = _FakeRecorder("run-pub")
    store_path = tmp_path / "candidates.sqlite3"

    run_pipeline_publishing(
        config=config,
        recorder=recorder,
        data_result=_FakeDataResult(),
        array_contract=_FakeArrayContract(),
        optimization_source=_FakeSource(),
        optimization_result=_result(),
        portfolio_builtin={"fees": 0.001},
        optimization_evidence={},
        store_path=store_path,
        metric_registry_fingerprint=None,
    )

    # publish_candidates writes in the pending state; activate to expose for querying.
    with CandidateStore(store_path) as store:
        store.activate_run("run-pub")
        top = store.top_candidates_by_run("run-pub")

    assert [row["role"] for row in top] == ["best", "median", "worst"]
    assert [row["ranking_metric_value"] for row in top] == [0.30, 0.20, 0.10]
