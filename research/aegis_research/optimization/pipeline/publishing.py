"""Pipeline publishing stage.

Turns the three representative candidates into role-tagged candidate rows,
resolves the winning component lock, and publishes them to the candidate store.
"""

from __future__ import annotations

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
from research.aegis_research.optimization.evidence import candidate_rows_from_result
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
    optimization_result: Any,
    portfolio_builtin: dict[str, Any],
    optimization_evidence: dict[str, Any],
    store_path: Path,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    """Build the three candidate rows, locks, and publish to the candidate store.

    Returns a dict with keys:
        candidate_rows, lock_records, candidate_store_provenance,
        optimization_evidence.
    """
    store_namespace = candidate_store_namespace()
    candidate_rows = candidate_rows_from_result(
        optimization_result,
        source_identity=optimization_source.evidence,
        data_identity=build_candidate_data_identity(data_result, array_contract),
        portfolio_policy=portfolio_builtin,
        store_namespace=store_namespace,
    )
    best_candidate = next(row for row in candidate_rows if row["role"] == "best")
    optimization_evidence["candidates"] = candidate_rows
    optimization_evidence["candidate_count"] = len({row["candidate_key"] for row in candidate_rows})
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
        best_candidate=best_candidate,
        optimization_source=optimization_source.evidence,
    )
    publish_candidates(
        store_path,
        run_id=recorder.manifest.run_id,
        candidate_rows=candidate_rows,
        ranking_metric=config.ranking.metric,
        provenance=candidate_store_provenance,
        lock_records=lock_records,
    )
    optimization_evidence["locks"] = lock_records
    recorder.manifest.evidence["optimization"] = optimization_evidence

    return {
        "candidate_rows": candidate_rows,
        "lock_records": lock_records,
        "candidate_store_provenance": candidate_store_provenance,
        "optimization_evidence": optimization_evidence,
    }
