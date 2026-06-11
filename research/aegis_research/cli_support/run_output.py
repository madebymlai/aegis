from __future__ import annotations

from typing import Any

from research.aegis_research.cli_support.output import run_refs
from research.aegis_research.configuration import ConfigSelectionEvidence


def build_run_payload(
    result: dict[str, Any],
    *,
    selection_evidence: ConfigSelectionEvidence,
) -> dict[str, Any]:
    """Single public entry: build the run success payload from raw sweep result
    and typed config-selection evidence.

    The selection block is projected from the evidence's existing manifest
    projection — no hand-written dict.
    """
    return {
        "selection": selection_evidence.manifest(),
        "run": run_refs(result),
        "artifacts": {
            "strategy_artifact_id": result.get("strategy_artifact_id"),
            "strategy_artifact_path": result.get("strategy_artifact_path"),
        },
        "candidate_store": {
            "path": result.get("candidate_store_path"),
        },
        "optimization": result.get("optimization", {}),
        "candidates": result.get("candidates", []),
    }
