"""Preflight and execute continuous Candidate replay plus block analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from research.aegis_research.configuration import (
    RunConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.continuous_evidence import (
    build_continuous_evidence,
)
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.observation_blocks import ObservationBlockAnalysis
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.portfolio_simulation import ResolvedBook
from research.aegis_research.optimization.preflight import (
    OptimizationPreflight,
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.ranking import OptimizationResult
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)
from research.aegis_research.provenance.manifest import RunStage


@dataclass(frozen=True)
class ExecutionResult:
    """Typed hand-off from the pipeline execution stage."""

    analysis: ObservationBlockAnalysis
    preflight: OptimizationPreflight
    evidence: Mapping[str, Any]
    selection_identity: Mapping[str, Any]

    @property
    def optimization_result(self) -> OptimizationResult:
        return self.analysis.result


def run_pipeline_execution(
    *,
    config: RunConfig,
    setup: SetupResult,
    book: ResolvedBook,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
) -> ExecutionResult:
    """Validate exact geometry, replay Candidates, and rank Observation Blocks."""
    run_evidence.enter_stage(RunStage.PREFLIGHT)
    try:
        preflight = build_preflight(
            source=setup.optimization_source,
            optimization=config.optimization,
            index=setup.run_data.replay_index,
            symbol_count=setup.run_data.instrument_count,
            metric_count=len(metric_registry.ids()),
            has_open_prices=True,
        )
        run_evidence.record(EvidenceSection.PREFLIGHT, preflight.diagnostics)
    except PreflightError as error:
        run_evidence.record(EvidenceSection.PREFLIGHT, error.diagnostics)
        run_evidence.persist_partial()
        raise OptimizationSourceError(str(error)) from error

    run_evidence.enter_stage(RunStage.EXECUTION)
    try:
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
        continuous_evidence = build_continuous_evidence(
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
        run_evidence.record(EvidenceSection.EXECUTION, continuous_evidence.execution)
    except Exception:
        run_evidence.persist_partial()
        raise

    return ExecutionResult(
        analysis=analysis,
        preflight=preflight,
        evidence=continuous_evidence.execution,
        selection_identity=continuous_evidence.selection_identity,
    )
