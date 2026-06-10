"""Optimization runner: source contract, preflight gate, candidate evidence, CV execution."""

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    build_component_optimization_source,
)

__all__ = [
    "CandidateStore",
    "CandidateStoreError",
    "ComponentSourceError",
    "build_component_optimization_source",
]
