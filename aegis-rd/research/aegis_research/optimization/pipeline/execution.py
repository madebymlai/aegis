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
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.observation_blocks import ObservationBlockAnalysis
from research.aegis_research.optimization.pipeline.setup import SetupResult
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
from research.aegis_research.optimization.window_evaluation import ResolvedBook


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
    # The public entry point rejects runs without an optimization block, so by the
    # time execution runs the optimization config is guaranteed present.
    assert config.optimization is not None
    try:
        preflight = build_preflight(
            source=setup.optimization_source,
            optimization=config.optimization,
            index=setup.arrays.signal.array("Close").index,
            symbol_count=len(setup.arrays.signal.array("Close").columns),
            metric_count=len(metric_registry.ids()),
            has_open_prices=True,
        )
        run_evidence.record(EvidenceSection.PREFLIGHT, preflight.diagnostics)
    except PreflightError as error:
        run_evidence.record(EvidenceSection.PREFLIGHT, error.diagnostics)
        run_evidence.fail(EvidenceFailureStage.PREFLIGHT, error)
        raise OptimizationSourceError(str(error)) from error

    try:
        analysis = execute_optimization(
            arrays=setup.arrays,
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
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.EXECUTION, error)
        raise

    return ExecutionResult(
        analysis=analysis,
        preflight=preflight,
        evidence=continuous_evidence.execution,
        selection_identity=continuous_evidence.selection_identity,
    )
