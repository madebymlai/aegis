"""Pipeline completion stage.

Writes the strategy artifact, marks the run as completed, activates
the candidate run in the store, and returns the final run result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from research.aegis_research.configuration import (
    RunConfig,
    lock_handle,
    to_builtin,
)
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.candidate_store_identity import (
    candidate_store_namespace,
)
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.publishing import PublishingResult
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.run_artifacts import (
    build_strategy_artifact_payload,
    write_strategy_artifact,
)
from research.aegis_research.optimization.run_data_contract import DataArrayContract
from research.aegis_research.provenance.recorder import RunRecorder
from research.aegis_research.run_data import RunData


def run_pipeline_completion(
    *,
    setup: SetupResult,
    publishing: PublishingResult,
    config: RunConfig,
    recorder: RunRecorder,
    run_data: RunData,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    """Write the strategy artifact, complete the run, and activate candidates.

    Returns the final run result dict with run refs, artifact metadata,
    candidate store path, optimization summary, and the three representative
    candidates.
    """
    try:
        optimization_evidence = run_evidence.optimization()
        execution = dict(optimization_evidence.get("execution", {}))
        preflight = dict(optimization_evidence["preflight"])
        store_namespace = candidate_store_namespace()
        artifact_payload = build_strategy_artifact_payload(
            strategy_evidence=setup.strategy_evidence,
            run_data=run_data,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            ranking={
                "metric": config.ranking.metric,
            },
            portfolio=to_builtin(config.portfolio),
            optimization=to_builtin(config.optimization),
            selection_metadata={
                "protocol": "continuous_future_in_past",
                "observation_block_bars": preflight["observation_block_bars"],
                "observation_block_bounds": preflight["observation_block_bounds"],
            },
            preflight=preflight,
            execution=execution,
            candidates=[to_builtin(record) for record in publishing.candidate_rows],
            candidate_store_path=store_namespace["path"],
            candidate_store_provenance=publishing.candidate_store_provenance,
        )
        write_strategy_artifact(recorder, artifact_payload)
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
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": str(recorder.run_dir / "strategy_run.json"),
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
