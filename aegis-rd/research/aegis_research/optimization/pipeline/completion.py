"""Complete the Run, activate its Candidates, and return the in-memory result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from research.aegis_research.configuration import RunConfig, lock_handle
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.publishing import PublishingResult
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.provenance.recorder import RunRecorder


def run_pipeline_completion(
    *,
    setup: SetupResult,
    publishing: PublishingResult,
    config: RunConfig,
    recorder: RunRecorder,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    """Complete the Run, activate Candidates, and return the final result.

    The result carries Run refs, CandidateStore path, optimization accounting,
    and the representative Candidate summaries directly from memory.
    """
    try:
        optimization_evidence = run_evidence.optimization()
        execution = dict(optimization_evidence.get("execution", {}))
        preflight = dict(optimization_evidence["preflight"])
        recorder.mark_run_completed()
        with CandidateStore(setup.store_path) as candidate_store:
            candidate_store.activate_run(recorder.manifest.run_id)
        return _completion_result(
            config=config,
            recorder=recorder,
            preflight=preflight,
            candidate_rows=publishing.candidate_rows,
            store_path=setup.store_path,
            execution=execution,
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.COMPLETION, error)
        raise


def _completion_result(
    *,
    config: RunConfig,
    recorder: RunRecorder,
    preflight: Mapping[str, Any],
    candidate_rows: Sequence[dict[str, Any]],
    store_path: Path,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    ranking_metric = config.ranking.metric
    return {
        **recorder.run_refs(),
        "candidate_store_path": str(store_path),
        "optimization": {
            "ranking_metric": ranking_metric,
            "protocol": "continuous_future_in_past",
            "observation_block_bars": preflight["observation_block_bars"],
            "observation_block_count": preflight["observation_block_count"],
            "candidate_count": len({row["candidate_key"] for row in candidate_rows}),
            "total": execution.get("candidate_accounting", {}).get("total", 0),
            "excluded_invalid": execution.get("candidate_accounting", {}).get(
                "excluded_invalid", 0
            ),
            "excluded_degenerate": execution.get("candidate_accounting", {}).get(
                "excluded_degenerate", 0
            ),
        },
        "candidates": [
            _candidate_summary(row, run_id=recorder.manifest.run_id) for row in candidate_rows
        ],
    }


def _candidate_summary(row: Mapping[str, Any], *, run_id: str) -> dict[str, Any]:
    return {
        "role": row["role"],
        "ordinal_rank": row["ordinal_rank"],
        "candidate_key": row["candidate_key"],
        "params": row["params"],
        "mean_rank": row["mean_rank"],
        "complete_period_metrics": row["complete_period_metrics"],
        "observation_block_metrics": row["observation_block_metrics"],
        "lock": lock_handle(run_id, row["role"]),
    }
