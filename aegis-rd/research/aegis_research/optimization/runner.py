"""Execute continuous Candidate paths and rank their Observation Block metrics."""

from __future__ import annotations

from collections.abc import Mapping

from vectorbtpro import vbt

from research.aegis_research.configuration import (
    OptimizationConfig,
    ReportConfig,
)
from research.aegis_research.metrics.registry import ResolvedMetrics
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
    metrics: ResolvedMetrics,
    min_trades: int,
    preflight: OptimizationPreflight,
) -> ObservationBlockAnalysis:
    """Execute the preflighted continuous replay and observational analysis."""
    _validate_source_param_names(source.params)

    try:
        paths = build_development_paths(
            run_data=run_data,
            source=source,
            optimization=optimization,
            book=book,
            report=report,
            metrics=metrics,
            min_trades=min_trades,
            plan=preflight.plan,
        )
    except CandidatePathError as error:
        raise OptimizationRunnerError(str(error)) from error
    return analyze_development_paths(
        paths,
        preflight.blocks,
        report=report,
        metrics=metrics,
    )


def _validate_source_param_names(params: Mapping[str, vbt.Param]) -> None:
    reserved = sorted(set(params) & OPTIMIZATION_PARAM_RESERVED_NAMES)
    if reserved:
        raise OptimizationRunnerError(
            f"optimization param names {reserved} are reserved for Aegis/VBT result "
            "coordinates; choose distinct parameter names"
        )
