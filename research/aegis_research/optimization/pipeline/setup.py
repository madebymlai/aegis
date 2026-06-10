"""Pipeline setup stage.

Resolves the optional top-level Lock, builds the optimization source and
evidence baseline for the strategy sweep.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataBundle,
    MarketDataResult,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
)
from research.aegis_research.optimization.candidate_publishing import (
    candidate_store_path,
)
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.evidence_ledger import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)
from research.aegis_research.optimization.lock_param_override import (
    overridden_component_params,
)
from research.aegis_research.optimization.lock_run import (
    ResolvedLockRun,
    resolve_lock_run,
)
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_evidence_payload,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
)
from research.aegis_research.run_splits import build_run_splits_result


def run_pipeline_setup(
    *,
    config: RunConfig,
    component_registry: FrozenComponentRegistry,
    data: MarketDataBundle,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    """Resolve the Lock, build the optimization source, and construct the evidence baseline.

    Returns a dict with keys:
        store_path, resolved_component_params, locked,
        optimization_source, strategy_evidence, close, split_result,
        optimization_builtin, portfolio_builtin.
    """
    # The public entry point rejects runs without an optimization block, so by the
    # time setup executes the optimization config is guaranteed present.
    assert config.optimization is not None
    store_path = candidate_store_path(config)
    lock_run = _resolve_lock_run(config, store_path=store_path)
    if lock_run is not None:
        # A locked Run reproduces one prior Candidate: every Component takes its
        # params from that Candidate and nothing is optimized.
        resolved_component_params = dict(lock_run.component_params)
        force_locked = True
        lock_evidence = _lock_evidence(config, lock_run)
    else:
        resolved_component_params = {}
        force_locked = False
        lock_evidence = None
    optimization_source = build_component_optimization_source(
        config,
        component_registry=component_registry,
        data=data,
        resolved_component_params=resolved_component_params,
        force_locked=force_locked,
    )
    strategy_evidence = optimization_source.evidence["strategy"]
    close = data.feature("Close")
    open_ = data.feature("Open")
    split_result = build_run_splits_result(close.index, config.optimization.split)
    optimization_builtin = to_builtin(config.optimization)
    portfolio_builtin = to_builtin(config.portfolio)
    run_evidence.initialize_optimization(
        _optimization_evidence_baseline(
            optimization_source=optimization_source,
            optimization_builtin=optimization_builtin,
            split_metadata=split_result.metadata,
            data_result=data_result,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            lock_evidence=lock_evidence,
        )
    )
    return {
        "store_path": store_path,
        "resolved_component_params": resolved_component_params,
        "locked": lock_run is not None,
        "optimization_source": optimization_source,
        "strategy_evidence": strategy_evidence,
        "close": close,
        "open_": open_,
        "split_result": split_result,
        "optimization_builtin": optimization_builtin,
        "portfolio_builtin": portfolio_builtin,
    }


def _resolve_lock_run(config: RunConfig, *, store_path: Any) -> ResolvedLockRun | None:
    if config.lock is None:
        return None
    with CandidateStore(store_path) as store:
        return resolve_lock_run(config.lock, store=store)


def _lock_evidence(config: RunConfig, lock_run: ResolvedLockRun) -> dict[str, Any]:
    assert config.lock is not None
    return {
        "mode": "reproduction",
        "run_id": config.lock.run_id,
        "candidate_id": config.lock.candidate_id,
        "resolved_candidate_key": lock_run.candidate_key,
        "provenance": lock_run.provenance,
        # Lock-wins (ADR-0006): the locked Candidate's params take effect; any per-Component
        # params: the author declared are overridden and recorded here — fail-loud, never a
        # silent drop — so the Manifest faithfully reports what ran.
        "overridden_params": overridden_component_params(config),
    }


def _optimization_evidence_baseline(
    *,
    optimization_source: Any,
    optimization_builtin: Mapping[str, Any],
    split_metadata: Mapping[str, Any],
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    lock_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": OPTIMIZATION_ROUTE_SCHEMA_VERSION,
        "contract": OPTIMIZATION_SOURCE_CONTRACT,
        "source": optimization_source.evidence,
        "param_names": list(optimization_source.params),
        "optimization": optimization_builtin,
        "split": split_metadata,
        "data": build_run_data_evidence_payload(data_result, array_contract),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "open_prices_available": True,
        "lock": lock_evidence,
    }
