"""Candidate Store identity and provenance helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.configuration import to_builtin
from research.aegis_research.optimization.run_data_contract import RunDataFacts

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
    facts: RunDataFacts,
    config: Any,
) -> dict[str, Any]:
    return {
        "schema_version": "candidate_store_provenance.v1",
        "run_id": recorder.manifest.run_id,
        "strategy_artifact_id": "strategy.run",
        "source": optimization_source,
        "data": facts.candidate_data_identity(),
        "portfolio": to_builtin(config.portfolio),
        "ranking": {
            "metric": config.ranking.metric,
        },
        "metric_registry_fingerprint": facts.metric_registry_fingerprint,
    }
