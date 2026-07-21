"""Typed results for regime-balanced Observation Block ranking."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluatedCandidate:
    """One Candidate described by block Metrics and its mean within-block rank."""

    params: Mapping[str, Any]
    score: float
    observation_block_metrics: Mapping[Any, Mapping[str, float | None]]
    metrics: Mapping[str, float | None]


@dataclass(frozen=True)
class OptimizationResult:
    """Fixed best/median/worst representatives from the admissible Candidate field."""

    best: EvaluatedCandidate
    median: EvaluatedCandidate
    worst: EvaluatedCandidate
    excluded_degenerate: int = 0
    excluded_invalid: int = 0
    total_candidates: int = 0


__all__ = ["EvaluatedCandidate", "OptimizationResult"]
