"""Resolve an optional Lock and construct the typed optimization source."""

from __future__ import annotations

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
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import RunConfig
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.run.data import RunData


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
) -> SetupResult:
    """Resolve the Lock and build the source used by execution."""
    store_path = candidate_store_path(config)
    lock_run = _resolve_lock_run(config, store_path=store_path)
    if lock_run is not None:
        # A locked Run reproduces one prior Candidate: every Component takes its
        # params from that Candidate and nothing is optimized.
        resolved_component_params = dict(lock_run.component_params)
        force_locked = True
    else:
        resolved_component_params = {}
        force_locked = False
    optimization_source = build_component_optimization_source(
        config,
        component_registry=component_registry,
        data=run_data.bundle,
        resolved_component_params=resolved_component_params,
        force_locked=force_locked,
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
