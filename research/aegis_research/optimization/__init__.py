"""Optimization runner: source contract, preflight gate, candidate evidence, CV execution."""

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)

__all__ = ["CandidateStore", "CandidateStoreError"]
