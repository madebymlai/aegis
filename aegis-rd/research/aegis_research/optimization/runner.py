"""Execute continuous Candidate paths and rank their observation-block evidence."""

from __future__ import annotations

from collections.abc import Mapping

from vectorbtpro import vbt

from research.aegis_research.configuration import (
    OptimizationConfig,
    RankingConfig,
    ReportConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_paths import (
    CandidatePathError,
    build_development_paths,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlockAnalysis,
    analyze_development_paths,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.optimization.source import (
    OPTIMIZATION_PARAM_RESERVED_NAMES,
    OptimizationSource,
)
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run.data import RunData


class OptimizationRunnerError(ValueError):
    pass


def execute_optimization(
    *,
    run_data: RunData,
    source: OptimizationSource,
    optimization: OptimizationConfig,
    book: ResolvedBook,
    report: ReportConfig,
    ranking: RankingConfig,
    metric_registry: FrozenMetricRegistry,
    preflight: OptimizationPreflight,
) -> ObservationBlockAnalysis:
    """Execute the preflighted continuous replay and observational analysis."""
    _validate_source_param_names(source.params)
    if ranking.metric not in metric_registry:
        raise OptimizationRunnerError(
            f"optimization ranking metric {ranking.metric!r} is not in the "
            f"metric registry: {sorted(metric_registry.ids())}"
        )

    try:
        paths = build_development_paths(
            run_data=run_data,
            source=source,
            optimization=optimization,
            book=book,
            report=report,
            metric_registry=metric_registry,
            min_trades=ranking.min_trades,
            ranking_metric=ranking.metric,
            plan=preflight.plan,
        )
    except CandidatePathError as error:
        raise OptimizationRunnerError(str(error)) from error
    return analyze_development_paths(
        paths,
        preflight.blocks,
        report=report,
        metric_registry=metric_registry,
        ranking_metric=ranking.metric,
    )


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )
