"""Materialize and replay every Candidate over one continuous Development path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig, ReportConfig
from research.aegis_research.metrics.accessors import central_metrics_from_grouped_accessors
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_validity import (
    Verdicts,
    classify_continuous_candidates,
)
from research.aegis_research.optimization.continuous_replay import (
    ContinuousReplayResult,
    replay_candidates,
)
from research.aegis_research.optimization.precompute import (
    CandidateKey,
    candidate_keys,
    canonical_param_order,
)
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OptimizationSource,
)
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run.data import RunData


class CandidatePathError(ValueError):
    """The continuous Candidate-path contract could not be satisfied."""


@dataclass(frozen=True)
class MaterializedCandidates:
    """One deterministic sampled grid with canonical Candidate identity."""

    param_names: tuple[str, ...]
    param_lists: Mapping[str, tuple[Any, ...]]
    keys: tuple[CandidateKey, ...]

    @property
    def count(self) -> int:
        return len(self.keys)

    def params_at(self, position: int) -> dict[str, Any]:
        return {name: self.param_lists[name][position] for name in self.param_names}


@dataclass(frozen=True)
class CandidateLookbacks:
    """Candidate lookbacks and their one common causal scoring boundary."""

    by_candidate: tuple[Mapping[str, int], ...]
    candidate_warmup_bars: tuple[int, ...]
    resolved_warmup_bars: int
    scored_start: int


@dataclass(frozen=True)
class DevelopmentPlan:
    """Materialized Candidate identity and lookbacks resolved before VBT execution."""

    candidates: MaterializedCandidates
    lookbacks: CandidateLookbacks


@dataclass(frozen=True)
class DevelopmentPaths:
    """Canonical continuous outputs handed to observational block analysis."""

    candidates: MaterializedCandidates
    lookbacks: CandidateLookbacks
    allocations: pd.DataFrame
    replay: ContinuousReplayResult
    full_period_metrics: pd.DataFrame
    verdicts: Verdicts


def materialize_candidates(
    params: Mapping[str, vbt.Param], optimization: OptimizationConfig
) -> MaterializedCandidates:
    """Materialize the grid once, applying deterministic VBT sampling if requested."""
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise CandidatePathError(
            f"optimization param names {reserved} are reserved for result coordinates"
        )
    options: dict[str, Any] = {}
    if optimization.search == "random":
        if optimization.random_subset is None or optimization.seed is None:
            raise CandidatePathError(
                "random optimization requires random_subset and seed for deterministic sampling"
            )
        options = {"random_subset": optimization.random_subset, "seed": optimization.seed}
    sampled = vbt.combine_params(dict(params), build_index=False, **options)
    param_names = tuple(canonical_param_order(sampled))
    param_lists = {name: tuple(sampled[name]) for name in param_names}
    keys = tuple(candidate_keys(param_lists))
    if not keys:
        raise CandidatePathError("optimization sampled Candidate grid must not be empty")
    return MaterializedCandidates(
        param_names=param_names,
        param_lists=param_lists,
        keys=keys,
    )


def build_development_paths(
    *,
    run_data: RunData,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    book: ResolvedBook,
    report: ReportConfig,
    metric_registry: FrozenMetricRegistry,
    min_trades: int,
    ranking_metric: str,
    plan: DevelopmentPlan | None = None,
) -> DevelopmentPaths:
    """Build every fixed Candidate path before any observational analysis."""
    if ranking_metric not in metric_registry:
        raise CandidatePathError(f"ranking metric {ranking_metric!r} is not in the metric registry")
    signal_close = run_data.bundle.array("Close")
    resolved_plan = (
        plan
        if plan is not None
        else plan_development(
            source=source,
            optimization=optimization,
            row_count=len(signal_close.index),
        )
    )
    candidates = resolved_plan.candidates
    lookbacks = resolved_plan.lookbacks

    param_lists = {name: list(values) for name, values in candidates.param_lists.items()}
    store = source.precompute(signal_close, candidates.count, **param_lists)
    invalid_keys = store.invalid_keys
    allocations = source.simulate(
        signal_close,
        store.window(slice(None), candidates.keys),
        candidates.count,
        **param_lists,
    )
    if allocations is vbt.NoResult:
        raise CandidatePathError("Candidate grid produced no portfolio allocations")
    if not isinstance(allocations, pd.DataFrame):
        raise CandidatePathError("Candidate allocations must be a pandas DataFrame")

    replay = replay_candidates(
        run_data.bundle.array("Close"),
        allocations,
        book,
        scored_start=lookbacks.scored_start,
        open_=run_data.bundle.array("Open"),
        periods_per_year=report.periods_per_year,
        distributions=run_data.distributions,
        currency_conversion=run_data.currency_conversion,
    )
    metrics = central_metrics_from_grouped_accessors(
        replay.portfolio,
        report,
        list(candidates.keys),
        list(candidates.param_names),
        metric_registry.extractors,
    )
    verdicts = classify_continuous_candidates(
        metrics,
        invalid_keys=invalid_keys,
        min_trades=min_trades,
        metric=ranking_metric,
    )
    return DevelopmentPaths(
        candidates=candidates,
        lookbacks=lookbacks,
        allocations=allocations,
        replay=replay,
        full_period_metrics=metrics,
        verdicts=verdicts,
    )


def plan_development(
    *,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    row_count: int,
) -> DevelopmentPlan:
    """Materialize the sampled grid and resolve its common start without execution."""
    candidates = materialize_candidates(source.params, optimization)
    return DevelopmentPlan(
        candidates=candidates,
        lookbacks=_resolve_lookbacks(candidates, source, row_count),
    )


def _resolve_lookbacks(
    candidates: MaterializedCandidates,
    source: OptimizationSource,
    row_count: int,
) -> CandidateLookbacks:
    by_candidate: list[Mapping[str, int]] = []
    candidate_warmups: list[int] = []
    for position in range(candidates.count):
        resolved = dict(source.resolve_lookbacks(candidates.params_at(position)))
        if not resolved:
            raise CandidatePathError(
                "lookback resolution must return at least one Component result"
            )
        for component, bars in resolved.items():
            if not isinstance(component, str) or not component:
                raise CandidatePathError("lookback Component names must be non-empty strings")
            if not isinstance(bars, int) or isinstance(bars, bool) or bars < 0:
                raise CandidatePathError(
                    f"lookback for Component {component!r} must be a non-negative integer"
                )
        by_candidate.append(resolved)
        candidate_warmups.append(max(resolved.values()))

    resolved_warmup = max(candidate_warmups)
    if resolved_warmup >= row_count:
        raise CandidatePathError("resolved Component lookback leaves no scored Development rows")
    return CandidateLookbacks(
        by_candidate=tuple(by_candidate),
        candidate_warmup_bars=tuple(candidate_warmups),
        resolved_warmup_bars=resolved_warmup,
        scored_start=resolved_warmup,
    )


__all__ = [
    "CandidateLookbacks",
    "CandidatePathError",
    "DevelopmentPaths",
    "DevelopmentPlan",
    "MaterializedCandidates",
    "build_development_paths",
    "materialize_candidates",
    "plan_development",
]
