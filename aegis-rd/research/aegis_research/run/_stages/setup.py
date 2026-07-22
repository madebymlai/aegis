"""Pipeline setup stage.

Resolves the optional top-level Lock, builds the optimization source and
evidence baseline for the strategy sweep.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.aegis_research.candidates.identity import (
    candidate_store_path,
)
from research.aegis_research.candidates.lock import (
    ResolvedLockRun,
    resolve_lock_run,
)
from research.aegis_research.candidates.lock_overrides import (
    overridden_component_params,
)
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_SOURCE_CONTRACT,
    OptimizationSource,
)
from research.aegis_research.run.data import RunData
from research.aegis_research.run.data_contract import (
    DataArrayContract,
    run_data_evidence_payload,
)
from research.aegis_research.run.evidence import (
    OPTIMIZATION_ROUTE_SCHEMA_VERSION,
    RunEvidence,
)


@dataclass(frozen=True)
class SetupResult:
    """Typed hand-off from the pipeline setup stage.

    The store path is an identity all stages must agree on; the optimization
    source is the product of Lock resolution and Component construction; and
    Arrays are the coherent two-view market value consumed by replay.
    """

    store_path: Path
    optimization_source: OptimizationSource
    run_data: RunData


def run_pipeline_setup(
    *,
    config: RunConfig,
    component_registry: FrozenComponentRegistry,
    run_data: RunData,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    run_evidence: RunEvidence,
) -> SetupResult:
    """Resolve the Lock, build the optimization source, and construct the evidence baseline."""
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
        data=run_data.bundle,
        resolved_component_params=resolved_component_params,
        force_locked=force_locked,
    )
    optimization_builtin = to_builtin(config.optimization)
    run_evidence.initialize_optimization(
        _optimization_evidence_baseline(
            optimization_source=optimization_source,
            optimization_builtin=optimization_builtin,
            selection_metadata={
                "protocol": "continuous_future_in_past",
                "observation_block_bars": config.optimization.observation_block_bars,
            },
            run_data=run_data,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            lock_evidence=lock_evidence,
        )
    )
    return SetupResult(
        store_path=store_path,
        optimization_source=optimization_source,
        run_data=run_data,
    )


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
    selection_metadata: Mapping[str, Any],
    run_data: RunData,
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
        "selection": selection_metadata,
        "data": run_data_evidence_payload(run_data, array_contract),
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "open_prices_available": True,
        "lock": lock_evidence,
    }
