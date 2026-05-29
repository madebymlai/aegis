"""Run artifacts.

Builds and persists the strategy run artifact payload
for orchestrated optimization runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from research.aegis_research.data_arrays import DataArrayContract
from research.aegis_research.optimization.run_data_contract import (
    build_run_data_evidence_payload,
)
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file

OPTIMIZATION_ARTIFACT_SCHEMA_VERSION = "optimization_artifact.v1"


def build_strategy_artifact_payload(
    *,
    strategy_evidence: Mapping[str, Any],
    data_result: Any,
    array_contract: DataArrayContract,
    ranking: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    optimization: Mapping[str, Any],
    split_metadata: Mapping[str, Any],
    preflight: Mapping[str, Any],
    execution: Mapping[str, Any],
    candidates: list[Mapping[str, Any]],
    resolved_locks: list[Mapping[str, Any]],
    lock_records: list[Mapping[str, Any]],
    candidate_store_path: str,
    candidate_store_provenance: Mapping[str, Any],
    metric_registry_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": OPTIMIZATION_ARTIFACT_SCHEMA_VERSION,
        "strategy": strategy_evidence,
        "data": build_run_data_evidence_payload(data_result, array_contract),
        "ranking": dict(ranking),
        "portfolio": dict(portfolio),
        "optimization": dict(optimization),
        "split": dict(split_metadata),
        "preflight": dict(preflight),
        "execution": dict(execution),
        "candidates": [dict(record) for record in candidates],
        "resolved_locks": list(resolved_locks),
        "locks": list(lock_records),
        "candidate_store": {
            "schema_version": "candidate_store_ref.v1",
            "path": candidate_store_path,
            "provenance": dict(candidate_store_provenance),
        },
        "metric_registry_fingerprint": metric_registry_fingerprint,
    }


def write_strategy_artifact(recorder: Any, payload: dict[str, Any]) -> None:
    plan_strategy_artifact(recorder)
    artifact_path = Path("strategy_run.json")
    recorder.artifacts.begin_artifact_write("strategy.run")
    full_path = recorder.run_dir / artifact_path
    atomic_write_json(full_path, payload)
    recorder.artifacts.complete_artifact(
        "strategy.run",
        content_hash=hash_file(full_path),
        size=full_path.stat().st_size,
        shape=strategy_artifact_shape(payload),
    )


def plan_strategy_artifact(recorder: Any) -> None:
    if find_strategy_artifact_record(recorder) is not None:
        return
    recorder.artifacts.plan_artifact(
        artifact_id="strategy.run",
        role="optimization_evidence",
        artifact_type="json",
        producer_stage="strategy_run",
        path="strategy_run.json",
        schema_version=OPTIMIZATION_ARTIFACT_SCHEMA_VERSION,
    )


def find_strategy_artifact_record(recorder: Any) -> dict[str, Any] | None:
    for artifact in recorder.manifest.artifacts:
        if artifact["id"] == "strategy.run":
            return artifact
    return None


def strategy_artifact_shape(payload: dict[str, Any]) -> dict[str, int]:
    shape: dict[str, int] = {
        "candidate_count": len(payload.get("candidates", [])),
    }
    if "split" in payload:
        shape["split_count"] = int(payload["split"].get("n_splits", 0))
    return shape
