"""Candidate publishing.

Persists the three representative candidates, their ranking, and component
locks into the local candidate store, then activates the run once the strategy
artifact has been written.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from research.aegis_research.config import to_builtin
from research.aegis_research.data_arrays import DataArrayContract
from research.aegis_research.optimization.candidate_store import (
    PUBLICATION_PENDING,
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.run_data_contract import (
    build_candidate_data_identity,
)


def candidate_store_path(config: Any) -> Path:
    return Path(config.output_dir) / ".candidate_store" / "candidates.sqlite3"


def candidate_store_namespace() -> dict[str, str]:
    return {
        "kind": "local_sqlite",
        "path": ".candidate_store/candidates.sqlite3",
    }


def build_candidate_store_provenance(
    recorder: Any,
    *,
    optimization_source: dict[str, Any],
    data_result: Any,
    array_contract: DataArrayContract,
    config: Any,
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "candidate_store_provenance.v1",
        "run_id": recorder.manifest.run_id,
        "strategy_artifact_id": "strategy.run",
        "source": optimization_source,
        "data": build_candidate_data_identity(data_result, array_contract),
        "portfolio": to_builtin(config.portfolio),
        "ranking": {
            "metric": config.ranking.metric,
            "min_weight": config.ranking.min_weight,
        },
        "metric_registry_fingerprint": metric_registry_fingerprint,
    }


def publish_candidates(
    store_path: str | Path,
    *,
    run_id: str,
    candidate_rows: Sequence[Mapping[str, Any]],
    ranking_metric: str,
    provenance: Mapping[str, Any],
    lock_records: Sequence[Mapping[str, Any]],
    publication_state: str = PUBLICATION_PENDING,
) -> None:
    with CandidateStore(store_path) as candidate_store:
        candidate_store.insert_completed_run(
            run_id=run_id,
            candidate_rows=candidate_rows,
            ranking_metric=ranking_metric,
            provenance=provenance,
            publication_state=publication_state,
        )
        for lock_record in lock_records:
            candidate_store.insert_lock(
                token=lock_record["token"],
                run_id=lock_record["run_id"],
                component_family=lock_record["component_family"],
                component_id=lock_record["component_id"],
                component_slot=lock_record["component_slot"],
                candidate_key=lock_record["candidate_key"],
                params=lock_record["params"],
                provenance=lock_record["provenance"],
                publication_state=publication_state,
            )


def activate_candidate_run(
    store_path: str | Path,
    run_id: str,
) -> None:
    try:
        with CandidateStore(store_path) as candidate_store:
            candidate_store.activate_run(run_id)
    except CandidateStoreError as error:
        raise CandidateStoreError(f"candidate_store_activation_failed: {error}") from error
