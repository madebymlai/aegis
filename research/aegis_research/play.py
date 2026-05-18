from __future__ import annotations

from typing import Any

from research.aegis_research.config import ResolvedLaneConfig, SourceRefConfig
from research.aegis_research.playbook_registry import (
    FrozenPlaybookRegistry,
    PlaybookSelection,
)
from research.aegis_research.playbook_registry.registry import execute_notebook_playbook


def run_play(
    resolved_config: ResolvedLaneConfig,
    *,
    playbook_registry: FrozenPlaybookRegistry,
) -> dict[str, Any]:
    config = resolved_config.config
    if config.lane != "play":
        raise ValueError("run_play requires a play lane config")
    play_config = config.play
    if play_config is None:
        raise ValueError("play lane config is missing play settings")

    results: list[dict[str, Any]] = []
    playbooks: list[dict[str, Any]] = []
    for ref in play_config.indicator_refs:
        if ref.source != "playbook":
            continue
        definition = playbook_registry.get(PlaybookSelection("indicators", ref.id))
        _assert_stage_supported(ref, definition.manifest.stages, play_config.stages)
        results.append(execute_notebook_playbook(definition, params=ref.params))
        playbooks.append(
            {
                "family": definition.family,
                "id": definition.id,
                "version": definition.manifest.version,
                "stages": list(definition.manifest.stages),
                "result_schema": definition.manifest.result_schema,
            }
        )

    return {
        "lane": "play",
        "evidence_type": "exploratory",
        "name": config.name,
        "playbooks": playbooks,
        "results": results,
        "ranking": {
            "metric": play_config.ranking.metric,
            "direction": play_config.ranking.direction,
            "rank_by": play_config.ranking.rank_by,
        },
    }


def _assert_stage_supported(
    ref: SourceRefConfig,
    supported_stages: tuple[str, ...],
    requested_stages: list[str],
) -> None:
    missing = sorted(set(requested_stages) - set(supported_stages))
    if missing:
        raise ValueError(f"playbook {ref.id!r} does not support stages: {missing}")
