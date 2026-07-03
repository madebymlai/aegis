"""Candidate Store identity and provenance helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.configuration import to_builtin
from research.aegis_research.optimization.run_data_contract import (
    DataArrayContract,
    build_candidate_data_identity,
)

CANDIDATE_STORE_RELATIVE_PATH = Path(".candidate_store") / "candidates.sqlite3"


def candidate_store_path(config: Any) -> Path:
    return Path(config.output_dir) / CANDIDATE_STORE_RELATIVE_PATH


def candidate_store_namespace() -> dict[str, str]:
    return {
        "kind": "local_sqlite",
        "path": CANDIDATE_STORE_RELATIVE_PATH.as_posix(),
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
