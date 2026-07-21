"""Unit tests for the pipeline publishing stage (three-candidate output)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, cast

import pandas as pd

from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.candidate_validity import Verdicts
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlockAnalysis,
    ObservationBlocks,
)
from research.aegis_research.optimization.param_namespace import (
    ComponentRef,
    encode,
)
from research.aegis_research.optimization.pipeline.execution import ExecutionResult
from research.aegis_research.optimization.pipeline.publishing import (
    PublishingResult,
    run_pipeline_publishing,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.factories import (
    make_run_data_facts,
    make_selection_identity,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)
from tests.support.research.aegis_research.test_doubles import (
    FakeArrayContract,
    FakeDataResult,
    FakeRecorder,
)

_FAMILY = "strategies"
_COMPONENT_ID = "demo.ma_cross"
_SLOT = "strategy:demo.ma_cross"
_STRATEGY_REF = ComponentRef(_FAMILY, _COMPONENT_ID, _SLOT)
_FAST_KEY = encode(_STRATEGY_REF, "fast_window")
_SLOW_KEY = encode(_STRATEGY_REF, "slow_window")


class _FakeSource:
    evidence: ClassVar[dict[str, Any]] = {
        "schema_version": "component_optimization_source.v2",
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
        observation_block_metrics={"block-000": {"total_return": score}},
        metrics={"total_return": score},
    )


def _result() -> OptimizationResult:
    return OptimizationResult(
        best=_candidate(5, 10, 0.30),
        median=_candidate(2, 10, 0.20),
        worst=_candidate(8, 20, 0.10),
    )


def _execution() -> ExecutionResult:
    result = _result()
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(2), ((0, 1), (1, 2)))
    analysis = ObservationBlockAnalysis(
        blocks=blocks,
        metric_matrices={},
        ranking_ranks=pd.DataFrame(),
        full_period_metrics=pd.DataFrame(),
        verdicts=Verdicts(),
        result=result,
    )
    return ExecutionResult(
        analysis=analysis,
        preflight=cast(OptimizationPreflight, None),
        evidence={},
        selection_identity=make_selection_identity(),
    )


def _run_evidence(recorder: FakeRecorder) -> RunEvidence:
    return RunEvidence(
        recorder.manifest.evidence,
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={"schema_version": OPTIMIZATION_ROUTE_SCHEMA_VERSION},
        persist=lambda: None,
    )


def test_publishing_writes_three_candidate_output_to_manifest(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path).config
    recorder = FakeRecorder("run-pub")
    store_path = tmp_path / "candidates.sqlite3"
    run_evidence = _run_evidence(recorder)

    out = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        facts=make_run_data_facts(
            data_result=FakeDataResult(),
            array_contract=FakeArrayContract(),
            metric_registry_fingerprint="fp-test",
        ),
        optimization_source=_FakeSource(),
        execution=_execution(),
        run_evidence=run_evidence,
        store_path=store_path,
    )

    assert isinstance(out, PublishingResult)
    candidate_rows = out.candidate_rows
    assert [row["role"] for row in candidate_rows] == ["best", "median", "worst"]
    assert [row["ordinal_rank"] for row in candidate_rows] == [1, 2, 3]

    manifest_optimization = recorder.manifest.evidence["optimization"]
    assert [row["role"] for row in manifest_optimization["candidates"]] == [
        "best",
        "median",
        "worst",
    ]
    assert manifest_optimization["candidate_count"] == 3


def test_publishing_persists_three_candidates_to_store(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path).config
    recorder = FakeRecorder("run-pub")
    store_path = tmp_path / "candidates.sqlite3"
    run_evidence = _run_evidence(recorder)

    run_pipeline_publishing(
        config=config,
        recorder=recorder,
        facts=make_run_data_facts(
            data_result=FakeDataResult(),
            array_contract=FakeArrayContract(),
        ),
        optimization_source=_FakeSource(),
        execution=_execution(),
        run_evidence=run_evidence,
        store_path=store_path,
    )

    # Publishing writes in the pending state; activate to expose for querying.
    with CandidateStore(store_path) as store:
        store.activate_run("run-pub")
        stored = [
            store.candidate_by_key(
                store.candidate_key_for_role("run-pub", role), run_id="run-pub"
            )
            for role in ("best", "median", "worst")
        ]

    assert [
        row["candidate"]["complete_period_metrics"]["total_return"] for row in stored
    ] == [0.30, 0.20, 0.10]
