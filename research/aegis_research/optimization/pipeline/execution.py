"""Pipeline execution stage.

Runs the preflight gate, executes the two-phase optimization, and records the
three-candidate result evidence for downstream stages.
"""

from __future__ import annotations

from dataclasses import dataclass

from research.aegis_research.configuration import (
    RunConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_evidence import result_evidence
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.ranking import OptimizationResult
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)


@dataclass(frozen=True)
class ExecutionResult:
    """Typed hand-off from the pipeline execution stage."""

    optimization_result: OptimizationResult


def run_pipeline_execution(
    *,
    config: RunConfig,
    setup: SetupResult,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
) -> ExecutionResult:
    """Execute the preflight gate and two-phase optimization sweep."""
    # The public entry point rejects runs without an optimization block, so by the
    # time execution runs the optimization config is guaranteed present.
    assert config.optimization is not None
    try:
        preflight = build_preflight(
            params=setup.optimization_source.params,
            optimization=config.optimization,
            splits=setup.split_result.splits,
            symbol_count=len(setup.close.columns),
            has_open_prices=True,
        )
        run_evidence.record(EvidenceSection.PREFLIGHT, preflight)
    except PreflightError as error:
        run_evidence.record(EvidenceSection.PREFLIGHT, error.diagnostics)
        run_evidence.fail(EvidenceFailureStage.PREFLIGHT, error)
        raise OptimizationSourceError(str(error)) from error

    try:
        optimization_result = execute_optimization(
            close=setup.close,
            open_=setup.open_,
            source=setup.optimization_source,
            optimization=config.optimization,
            portfolio=config.portfolio,
            report=config.report,
            ranking=config.ranking,
            metric_registry=metric_registry,
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.EXECUTION, error)
        raise

    run_evidence.record(EvidenceSection.EXECUTION, result_evidence(optimization_result))

    return ExecutionResult(optimization_result=optimization_result)
