from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.aegis_research.configuration import lock_handle
from research.aegis_research.run.identity import RunId


@dataclass(frozen=True)
class OptimizationSummary:
    ranking_metric: str
    observation_block_bars: int
    observation_block_count: int
    candidate_count: int
    total: int
    excluded_invalid: int
    excluded_degenerate: int
    protocol: str = "continuous_future_in_past"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranking_metric": self.ranking_metric,
            "protocol": self.protocol,
            "observation_block_bars": self.observation_block_bars,
            "observation_block_count": self.observation_block_count,
            "candidate_count": self.candidate_count,
            "total": self.total,
            "excluded_invalid": self.excluded_invalid,
            "excluded_degenerate": self.excluded_degenerate,
        }


@dataclass(frozen=True)
class CandidateSummary:
    role: str
    ordinal_rank: int
    candidate_key: str
    params: Mapping[str, Any]
    mean_rank: float | None
    complete_period_metrics: Mapping[str, Any]
    observation_block_metrics: Mapping[str, Any]
    lock: str

    @classmethod
    def from_candidate(cls, candidate: Mapping[str, Any], *, run_id: RunId) -> CandidateSummary:
        role = str(candidate["role"])
        return cls(
            role=role,
            ordinal_rank=int(candidate["ordinal_rank"]),
            candidate_key=str(candidate["candidate_key"]),
            params=dict(candidate["params"]),
            mean_rank=candidate["mean_rank"],
            complete_period_metrics=dict(candidate["complete_period_metrics"]),
            observation_block_metrics=dict(candidate["observation_block_metrics"]),
            lock=lock_handle(str(run_id), role),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "ordinal_rank": self.ordinal_rank,
            "candidate_key": self.candidate_key,
            "params": dict(self.params),
            "mean_rank": self.mean_rank,
            "complete_period_metrics": dict(self.complete_period_metrics),
            "observation_block_metrics": dict(self.observation_block_metrics),
            "lock": self.lock,
        }


@dataclass(frozen=True)
class RunResult:
    run_id: RunId
    candidate_store_path: Path
    optimization: OptimizationSummary
    candidates: tuple[CandidateSummary, ...]

    @classmethod
    def create(
        cls,
        *,
        run_id: RunId,
        candidate_store_path: Path,
        optimization: OptimizationSummary,
        candidates: Sequence[Mapping[str, Any]],
    ) -> RunResult:
        return cls(
            run_id=run_id,
            candidate_store_path=candidate_store_path,
            optimization=optimization,
            candidates=tuple(
                CandidateSummary.from_candidate(candidate, run_id=run_id)
                for candidate in candidates
            ),
        )


__all__ = ["CandidateSummary", "OptimizationSummary", "RunResult"]
