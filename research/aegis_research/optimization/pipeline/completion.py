"""Pipeline completion stage.

Writes the strategy artifact, marks the run as completed, activates
the candidate run in the store, and returns the final run result.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from research.aegis_research.config import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataResult,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
)
from research.aegis_research.optimization.candidate_publishing import (
    activate_candidate_run,
)
from research.aegis_research.optimization.evidence import (
    candidate_held_out_headline,
    held_out_warning,
)
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    RunEvidence,
)
from research.aegis_research.optimization.run_artifacts import (
    build_strategy_artifact_payload,
    write_strategy_artifact,
)
from research.aegis_research.provenance.recorder import RunRecorder


def run_pipeline_completion(
    *,
    config: RunConfig,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    strategy_evidence: Mapping[str, Any],
    optimization_builtin: Mapping[str, Any],
    portfolio_builtin: Mapping[str, Any],
    split_result: Any,
    run_evidence: RunEvidence,
    candidate_rows: list[Mapping[str, Any]],
    resolved_locks: list[Mapping[str, Any]],
    lock_records: list[Mapping[str, Any]],
    candidate_store_provenance: Mapping[str, Any],
    store_path: Path,
    store_namespace: Mapping[str, str],
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    """Write the strategy artifact, complete the run, and activate candidates.

    Returns the final run result dict with run refs, artifact metadata,
    candidate store path, lock records, optimization summary, and the three
    representative candidates.
    """
    try:
        optimization_evidence = run_evidence.optimization()
        artifact_payload = build_strategy_artifact_payload(
            strategy_evidence=strategy_evidence,
            data_result=data_result,
            array_contract=array_contract,
            ranking={
                "metric": config.ranking.metric,
                "min_weight": config.ranking.min_weight,
            },
            portfolio=portfolio_builtin,
            optimization=optimization_builtin,
            split_metadata=split_result.metadata,
            preflight=optimization_evidence["preflight"],
            execution=dict(optimization_evidence.get("execution", {})),
            candidates=[to_builtin(record) for record in candidate_rows],
            resolved_locks=resolved_locks,
            lock_records=lock_records,
            candidate_store_path=store_namespace["path"],
            candidate_store_provenance=candidate_store_provenance,
            metric_registry_fingerprint=metric_registry_fingerprint,
        )
        write_strategy_artifact(recorder, artifact_payload)
        recorder.mark_run_completed()
        activate_candidate_run(store_path, recorder.manifest.run_id)
        ranking_metric = config.ranking.metric
        best_row = next(row for row in candidate_rows if row["role"] == "best")
        return {
            **build_run_refs(recorder),
            "strategy_artifact_id": "strategy.run",
            "strategy_artifact_path": str(recorder.run_dir / "strategy_run.json"),
            "candidate_store_path": str(store_path),
            "locks": lock_records,
            "optimization": {
                "ranking_metric": ranking_metric,
                "min_weight": config.ranking.min_weight,
                "split_count": split_result.metadata["n_splits"],
                "candidate_count": len({row["candidate_key"] for row in candidate_rows}),
                "held_out_warning": held_out_warning(
                    candidate_held_out_headline(best_row, metric=ranking_metric)
                ),
            },
            "candidates": [
                _candidate_summary(row, ranking_metric=ranking_metric) for row in candidate_rows
            ],
        }
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.COMPLETION, error)
        raise


def _candidate_summary(row: Mapping[str, Any], *, ranking_metric: str) -> dict[str, Any]:
    return {
        "role": row["role"],
        "rank": row["rank"],
        "candidate_key": row["candidate_key"],
        "params": row["params"],
        "score": row["score"],
        "metrics": row["metrics"],
        "selection_metrics": row["selection_metrics"],
        "held_out_metrics": row["held_out_metrics"],
        "held_out_metrics_mean": row["held_out_metrics_mean"],
        "held_out_headline": candidate_held_out_headline(row, metric=ranking_metric),
    }


def build_run_refs(recorder: RunRecorder) -> dict[str, Any]:
    return {
        "run_id": recorder.manifest.run_id,
        "run_dir": str(recorder.run_dir),
        "manifest_path": str(recorder.manifest_path),
        "status": recorder.manifest.status,
        "started_at": recorder.manifest.started_at,
        "finished_at": recorder.manifest.finished_at,
    }
