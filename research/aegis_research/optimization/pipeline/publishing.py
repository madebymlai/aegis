"""Pipeline publishing stage.

Evaluates candidates from the optimization run, builds the leaderboard,
and publishes results to the candidate store.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from research.aegis_research.config import (
    RunConfig,
)
from research.aegis_research.data import (
    MarketDataResult,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
)
from research.aegis_research.optimization.candidate_publishing import (
    build_candidate_store_provenance,
    candidate_store_namespace,
    publish_candidates,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import build_optimization_leaderboard
from research.aegis_research.optimization.lock_resolution import (
    build_component_lock_records,
)
from research.aegis_research.optimization.run_data_contract import (
    build_candidate_data_identity,
)
from research.aegis_research.provenance.recorder import RunRecorder


def run_pipeline_publishing(
    *,
    config: RunConfig,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    optimization_source: Any,
    optimization_run: Any,
    run_payload: Mapping[str, Any],
    split_result: Any,
    portfolio_builtin: Mapping[str, Any],
    optimization_evidence: dict[str, Any],
    store_path: Path,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    """Build candidate rows, leaderboard, locks, and publish to the candidate store.

    Returns a dict with keys:
        candidate_rows, leaderboard, lock_records,
        candidate_store_provenance, optimization_evidence.
    """
    store_namespace = candidate_store_namespace()
    candidate_rows = candidate_rows_from_param_index(
        optimization_run.evaluated_index,
        source_identity=optimization_source.evidence,
        data_identity=build_candidate_data_identity(data_result, array_contract),
        portfolio_policy=portfolio_builtin,
        store_namespace=store_namespace,
        coordinate_levels=("split", "set", "symbol"),
    )
    optimization_evidence["candidate_count"] = len(candidate_rows)
    optimization_evidence["sampled_row_count"] = len(run_payload["sampled_rows"]["rows"])
    optimization_evidence["sampled_rows_source"] = optimization_run.sampled_rows_source
    split_held_out_row_counts = {
        i: len(split.held_out_index) for i, split in enumerate(split_result.splits)
    }
    leaderboard = build_optimization_leaderboard(
        selection=optimization_run.selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts=split_held_out_row_counts,
        ranking_metric=optimization_run.ranking_metric,
        ranking_direction=optimization_run.ranking_direction,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    candidate_store_provenance = build_candidate_store_provenance(
        recorder,
        optimization_source=optimization_source.evidence,
        data_result=data_result,
        array_contract=array_contract,
        config=config,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )
    lock_records = build_component_lock_records(
        run_id=recorder.manifest.run_id,
        leaderboard=leaderboard,
        optimization_source=optimization_source.evidence,
    )
    publish_candidates(
        store_path,
        run_id=recorder.manifest.run_id,
        candidate_rows=candidate_rows,
        leaderboard=leaderboard,
        provenance=candidate_store_provenance,
        lock_records=lock_records,
    )
    optimization_evidence["locks"] = lock_records
    recorder.manifest.evidence["optimization"] = optimization_evidence

    return {
        "candidate_rows": candidate_rows,
        "leaderboard": leaderboard,
        "lock_records": lock_records,
        "candidate_store_provenance": candidate_store_provenance,
        "optimization_evidence": optimization_evidence,
    }
