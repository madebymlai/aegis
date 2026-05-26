"""Optimization runner: source contract, preflight gate, candidate evidence, CV execution."""

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    build_component_optimization_source,
    component_param_key,
    component_param_slices,
    component_ref_key,
    parse_component_param_key,
)
from research.aegis_research.optimization.lock import (
    ComponentLockRef,
    LockResolutionError,
    ResolvedLock,
    resolve_component_lock,
)

__all__ = [
    "CandidateStore",
    "CandidateStoreError",
    "ComponentLockRef",
    "ComponentSourceError",
    "LockResolutionError",
    "ResolvedLock",
    "build_component_optimization_source",
    "component_param_key",
    "component_param_slices",
    "component_ref_key",
    "parse_component_param_key",
    "resolve_component_lock",
]
