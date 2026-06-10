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
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataResult,
)
from research.aegis_research.optimization.candidate_evidence import (
    candidate_held_out_headline,
    held_out_warning,
)
from research.aegis_research.optimization.candidate_publishing import (
    activate_candidate_run,
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
from research.aegis_research.run_splits import RunSplitsResult


def run_pipeline_completion(
    *,
    setup: SetupResult,
    publishing: PublishingResult,
    config: RunConfig,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    run_evidence: RunEvidence,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    """Write the strategy artifact, complete the run, and activate candidates.

    Returns the final run result dict with run refs, artifact metadata,
    candidate store path, optimization summary, and the three representative
    candidates.
    """
    try:
        optimization_evidence = run_evidence.optimization()
        execution = dict(optimization_evidence.get("execution", {}))
        store_namespace = candidate_store_namespace()
        artifact_payload = build_strategy_artifact_payload(
            strategy_evidence=setup.strategy_evidence,
            data_result=data_result,
            array_contract=array_contract,
            ranking={
                "metric": config.ranking.metric,
                "min_weight": config.ranking.min_weight,
            },
            portfolio=to_builtin(config.portfolio),
            optimization=to_builtin(config.optimization),
            split_metadata=setup.split_result.metadata,
            preflight=optimization_evidence["preflight"],
            execution=execution,
            candidates=[to_builtin(record) for record in publishing.candidate_rows],
            candidate_store_path=store_namespace["path"],
            candidate_store_provenance=publishing.candidate_store_provenance,
            metric_registry_fingerprint=metric_registry_fingerprint,
        )
        write_strategy_artifact(recorder, artifact_payload)
        recorder.mark_run_completed()
        activate_candidate_run(setup.store_path, recorder.manifest.run_id)
        return _completion_result(
            config=config,
            recorder=recorder,
            split_result=setup.split_result,
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
    split_result: RunSplitsResult,
    candidate_rows: Sequence[dict[str, Any]],
    store_path: Path,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    ranking_metric = config.ranking.metric
    best_row = next(row for row in candidate_rows if row["role"] == "best")
    return {
        **build_run_refs(recorder),
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": str(recorder.run_dir / "strategy_run.json"),
        "candidate_store_path": str(store_path),
        "optimization": {
            "ranking_metric": ranking_metric,
            "min_weight": config.ranking.min_weight,
            "split_count": split_result.metadata["n_splits"],
            "candidate_count": len({row["candidate_key"] for row in candidate_rows}),
            "total": execution.get("total", 0),
            "excluded_invalid": execution.get("excluded_invalid", 0),
            "excluded_degenerate": execution.get("excluded_degenerate", 0),
            "held_out_warning": held_out_warning(
                candidate_held_out_headline(best_row, metric=ranking_metric)
            ),
        },
        "candidates": [
            _candidate_summary(row, ranking_metric=ranking_metric) for row in candidate_rows
        ],
    }


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
