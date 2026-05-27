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
    optimization_evidence: Mapping[str, Any],
    run_payload: Mapping[str, Any],
    candidate_rows: list[Mapping[str, Any]],
    leaderboard: Mapping[str, Any],
    resolved_locks: list[Mapping[str, Any]],
    lock_records: list[Mapping[str, Any]],
    candidate_store_provenance: Mapping[str, Any],
    store_path: Path,
    store_namespace: Mapping[str, str],
    optimization_run: Any,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    """Write the strategy artifact, complete the run, and activate candidates.

    Returns the final run result dict with run refs, artifact metadata,
    candidate store path, lock records, optimization summary, and leaderboard.
    """
    artifact_payload = build_strategy_artifact_payload(
        strategy_evidence=strategy_evidence,
        data_result=data_result,
        array_contract=array_contract,
        ranking={
            "metric": config.ranking.metric,
            "direction": config.ranking.direction,
            "secondary_metrics": list(config.ranking.secondary_metrics),
        },
        portfolio=portfolio_builtin,
        optimization=optimization_builtin,
        split_metadata=split_result.metadata,
        preflight=optimization_evidence["preflight"],
        execution=run_payload,
        candidates=[to_builtin(record) for record in candidate_rows],
        leaderboard=leaderboard,
        resolved_locks=resolved_locks,
        lock_records=lock_records,
        candidate_store_path=store_namespace["path"],
        candidate_store_provenance=candidate_store_provenance,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    write_strategy_artifact(recorder, artifact_payload)
    recorder.mark_run_completed()
    activate_candidate_run(store_path, recorder.manifest.run_id)
    return {
        **build_run_refs(recorder),
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": str(recorder.run_dir / "strategy_run.json"),
        "candidate_store_path": str(store_path),
        "locks": lock_records,
        "optimization": {
            "ranking_metric": optimization_run.ranking_metric,
            "ranking_direction": optimization_run.ranking_direction,
            "split_count": split_result.metadata["n_splits"],
            "selection_row_count": len(optimization_run.selection),
            "candidate_count": len(candidate_rows),
        },
        "leaderboard": leaderboard,
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
