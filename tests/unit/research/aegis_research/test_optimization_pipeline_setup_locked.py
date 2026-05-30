"""Unit tests for locked-run behavior in the pipeline setup stage.

A Run Config carrying a top-level ``lock: {run_id, candidate_id}`` reproduces one prior
Candidate: setup resolves every Component's params from that Candidate, performs no
optimization (a single pinned Candidate, zero free params), and records reproduction
Evidence that the Run was not a fresh optimization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from research.aegis_research.config import resolve_run_config
from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import FIXED_CANDIDATE_PARAM
from research.aegis_research.optimization.evidence import candidate_rows_from_result
from research.aegis_research.optimization.evidence_ledger import RunEvidence
from research.aegis_research.optimization.pipeline.setup import run_pipeline_setup
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_array_contract,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)


class _FakeData:
    def feature(self, name: str) -> Any:
        import pandas as pd

        return pd.DataFrame({0: [float(i) for i in range(120)]})


class _FakeDataResult:
    class quality:
        state = "ok"

    metadata: ClassVar[dict[str, Any]] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "loaded_arrays": ["Close", "Open"],
        "effective_arrays": ["OHLCV"],
        "shape": {"rows": 120},
    }


def _run_evidence() -> RunEvidence:
    return RunEvidence(
        {},
        component_registry_fingerprint="registry-fp",
        data_arrays={},
        optimization={},
        persist=lambda: None,
    )


def _locked_raw_config(candidate_key: str) -> dict[str, Any]:
    from research.aegis_research.config import CONFIG_SCHEMA_VERSION

    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "locked_run_fixture",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"target_exposure_cap": 1.0},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 40, "offset": 40, "split": 0.5},
                "max_splits": 2,
            },
        },
        "lock": {"run_id": "run-a", "candidate_id": candidate_key},
    }


def _seed_candidate_store(config: Any) -> str:
    store_path = candidate_store_path(config)
    candidate = EvaluatedCandidate(
        params={},
        score=0.25,
        selection_metrics={0: {"total_return": 0.25}},
        metrics={"total_return": 0.25},
        held_out_metrics={0: {"total_return": 0.25}},
    )
    rows = candidate_rows_from_result(
        OptimizationResult(best=candidate, median=candidate, worst=candidate),
        source_identity=_source_evidence(),
        data_identity={"source": "synthetic", "symbols": ["SYN"], "timeframe": "1D"},
        portfolio_policy={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    candidate_key = rows[0]["candidate_key"]
    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id="run-a",
            candidate_rows=rows,
            ranking_metric="total_return",
            provenance={"run_id": "run-a", "source": _source_evidence()},
        )
    return candidate_key


def _source_evidence() -> dict[str, Any]:
    return {
        "schema_version": "component_optimization_source.v1",
        "source": "component",
        "strategy": {
            "family": "strategies",
            "slot": "strategy",
            "id": "demo.strategy",
            "version": "1.0.0",
            "fixed_params": {},
            "param_keys": {},
        },
        "indicators": [
            {
                "family": "indicators",
                "slot": "demo.returns",
                "id": "demo.returns",
                "version": "1.0.0",
                "fixed_params": {},
                "param_keys": {},
            }
        ],
    }


def _resolved_locked_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    base = build_resolved_run_config(tmp_path)
    candidate_key = _seed_candidate_store(base.config)
    raw = _locked_raw_config(candidate_key)
    return resolve_run_config(raw, component_registry=base.component_registry)


def test_locked_setup_resolves_every_component_from_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _resolved_locked_config(tmp_path, monkeypatch)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
    )

    params = result["resolved_component_params"]
    assert ("strategies", "demo.strategy", "strategy") in params
    assert ("indicators", "demo.returns", "demo.returns") in params


def test_locked_setup_performs_no_optimization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _resolved_locked_config(tmp_path, monkeypatch)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=_run_evidence(),
    )

    # A locked run pins a single Candidate: no free parameters remain to sweep.
    assert list(result["optimization_source"].params) == [FIXED_CANDIDATE_PARAM]


def test_locked_setup_records_reproduction_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _resolved_locked_config(tmp_path, monkeypatch)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    run_evidence = _run_evidence()
    run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=run_evidence,
    )

    evidence = run_evidence.optimization()
    lock_evidence = evidence["lock"]
    assert lock_evidence is not None
    assert lock_evidence["run_id"] == "run-a"
    assert lock_evidence["candidate_id"] == config.lock.candidate_id
    assert lock_evidence["mode"] == "reproduction"


def test_unlocked_setup_has_no_lock_evidence(
    tmp_path: Path,
) -> None:
    resolved = build_resolved_run_config(tmp_path)
    config = resolved.config
    array_contract = build_run_data_array_contract(config, resolved.component_registry)

    run_evidence = _run_evidence()
    run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        data=_FakeData(),
        data_result=_FakeDataResult(),
        array_contract=array_contract,
        metric_registry_fingerprint=None,
        run_evidence=run_evidence,
    )

    assert run_evidence.optimization()["lock"] is None
