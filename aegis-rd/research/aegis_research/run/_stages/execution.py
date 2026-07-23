"""Preflight and execute continuous Candidate replay plus block analysis."""

from __future__ import annotations

from dataclasses import dataclass

from research.aegis_research.configuration import (
    RunConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.observation_blocks import ObservationBlockAnalysis
from research.aegis_research.optimization.preflight import (
    OptimizationPreflight,
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.ranking import OptimizationResult
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.selection_identity import build_selection_identity
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run._stages.setup import SetupResult


@dataclass(frozen=True)
class ExecutionResult:
    """Typed hand-off from the pipeline execution stage."""

    analysis: ObservationBlockAnalysis
    preflight: OptimizationPreflight
    selection_identity: dict[str, object]

    @property
    def optimization_result(self) -> OptimizationResult:
        return self.analysis.result


def run_pipeline_execution(
    *,
    config: RunConfig,
    setup: SetupResult,
    book: ResolvedBook,
    metric_registry: FrozenMetricRegistry,
) -> ExecutionResult:
    """Validate exact geometry, replay Candidates, and rank Observation Blocks."""
    try:
        preflight = build_preflight(
            source=setup.optimization_source,
            optimization=config.optimization,
            index=setup.run_data.replay_index,
            symbol_count=setup.run_data.instrument_count,
            metric_count=len(metric_registry.ids()),
            has_open_prices=True,
        )
    except PreflightError as error:
        raise OptimizationSourceError(str(error)) from error

    analysis = execute_optimization(
        run_data=setup.run_data,
        source=setup.optimization_source,
        optimization=config.optimization,
        book=book,
        report=config.report,
        ranking=config.ranking,
        metric_registry=metric_registry,
        preflight=preflight,
    )
    selection_identity = build_selection_identity(
        analysis=analysis,
        preflight=preflight,
        optimization=config.optimization,
        metric_registry=metric_registry,
        ranking=config.ranking,
        report=config.report,
        direction=config.portfolio.direction,
        fill_timing=config.portfolio.fill_timing,
        data_start=config.data.start,
    )

    return ExecutionResult(
        analysis=analysis,
        preflight=preflight,
        selection_identity=dict(selection_identity),
    )
