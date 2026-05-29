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
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import (
    OptimizationSourceError,
)
from research.aegis_research.provenance.recorder import RunRecorder


def run_pipeline_execution(
    *,
    config: RunConfig,
    optimization_source: Any,
    close: pd.DataFrame,
    split_result: Any,
    optimization_evidence: dict[str, Any],
    recorder: RunRecorder,
) -> dict[str, Any]:
    """Execute the preflight gate and two-phase optimization sweep.

    Returns a dict with keys:
        optimization_result, optimization_evidence.
    """
    try:
        optimization_evidence["preflight"] = build_preflight(
            params=optimization_source.params,
            optimization=config.optimization,
            split_result=split_result,
            symbol_count=len(close.columns),
            has_open_prices=True,
        )
    except PreflightError as error:
        optimization_evidence["preflight"] = error.diagnostics
        optimization_evidence["preflight_failure"] = {
            "error_type": type(error).__name__,
            "message": str(error),
        }
        recorder.manifest.evidence["optimization"] = optimization_evidence
        recorder.persist()
        raise OptimizationSourceError(str(error)) from error

    try:
        optimization_result = execute_optimization(
            close=close,
            source=optimization_source,
            optimization=config.optimization,
            portfolio=config.portfolio,
            report=config.report,
            ranking=config.ranking,
        )
    except Exception as error:
        optimization_evidence["execution_failure"] = {
            "error_type": type(error).__name__,
            "message": str(error)[:1000],
        }
        recorder.manifest.evidence["optimization"] = optimization_evidence
        recorder.persist()
        raise

    optimization_evidence["execution"] = result_evidence(optimization_result)

    return {
        "optimization_result": optimization_result,
        "optimization_evidence": optimization_evidence,
    }
