"""Candidate Store identity and provenance helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.configuration import to_builtin
from research.aegis_research.run.data import RunData
from research.aegis_research.run.data_contract import (
    DataArrayContract,
    candidate_data_identity,
)

CANDIDATE_STORE_RELATIVE_PATH = Path(".candidate_store") / "candidates.sqlite3"
CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION = "candidate_store_provenance.v3"


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
    run_data: RunData,
    array_contract: DataArrayContract,
    config: Any,
    metric_registry_fingerprint: str | None,
    selection_identity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
        "run_id": recorder.manifest.run_id,
        "source": optimization_source,
        "data": candidate_data_identity(run_data, array_contract),
        "portfolio": to_builtin(config.portfolio),
        "ranking": {
            "metric": config.ranking.metric,
        },
        "metric_registry_fingerprint": metric_registry_fingerprint,
        "selection_identity": selection_identity,
    }
