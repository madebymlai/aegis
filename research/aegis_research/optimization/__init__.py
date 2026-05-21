"""Optimization runner: source contract, preflight gate, candidate evidence, CV execution."""

from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.promotion import (
    ComponentPromotionRef,
    PromotionResolutionError,
    ResolvedPromotion,
    resolve_component_promotion,
)

__all__ = [
    "CandidateStore",
    "CandidateStoreError",
    "ComponentPromotionRef",
    "PromotionResolutionError",
    "ResolvedPromotion",
    "resolve_component_promotion",
]
