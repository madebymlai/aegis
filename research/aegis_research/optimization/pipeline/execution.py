"""Pipeline execution stage.

Runs the preflight gate, executes the two-phase optimization, and records the
three-candidate result evidence for downstream stages.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.config import (
    RunConfig,
)
from research.aegis_research.optimization.evidence import result_evidence
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)


def run_pipeline_execution(
    *,
    config: RunConfig,
    optimization_source: Any,
    close: pd.DataFrame,
    open_: pd.DataFrame,
    split_result: Any,
    metric_registry: Any,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    """Execute the preflight gate and two-phase optimization sweep.

    Returns a dict with key:
        optimization_result.
    """
    try:
        preflight = build_preflight(
            params=optimization_source.params,
            optimization=config.optimization,
            split_result=split_result,
            symbol_count=len(close.columns),
            has_open_prices=True,
        )
        run_evidence.record(EvidenceSection.PREFLIGHT, preflight)
    except PreflightError as error:
        run_evidence.record(EvidenceSection.PREFLIGHT, error.diagnostics)
        run_evidence.fail(EvidenceFailureStage.PREFLIGHT, error)
        raise OptimizationSourceError(str(error)) from error

    try:
        optimization_result = execute_optimization(
            close=close,
            open_=open_,
            source=optimization_source,
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

    return {
        "optimization_result": optimization_result,
    }
