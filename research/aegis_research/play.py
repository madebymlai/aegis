from __future__ import annotations

from typing import Any

from research.aegis_research.config import ResolvedLaneConfig, SourceRefConfig
from research.aegis_research.play_artifacts import PlayArtifactStore
from research.aegis_research.playbook_registry import (
    FrozenPlaybookRegistry,
    PlaybookRegistryError,
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

    store = PlayArtifactStore(config.output_dir)
    results: list[dict[str, Any]] = []
    playbooks: list[dict[str, Any]] = []
    try:
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
        artifact_refs = store.write_success(
            play_name=config.name,
            ranking={
                "metric": play_config.ranking.metric,
                "direction": play_config.ranking.direction,
                "rank_by": play_config.ranking.rank_by,
            },
            variant_records=_variant_records(results),
            backup=play_config.backup_last_run,
            metadata={"playbooks": playbooks},
        )
    except PlaybookRegistryError:
        raise
    except Exception as error:
        store.write_failed_attempt(config.name, error)
        raise

    return {
        "lane": "play",
        "evidence_type": "exploratory",
        "name": config.name,
        "playbooks": playbooks,
        "results": results,
        "artifacts": artifact_refs,
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


def _variant_records(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for result in results:
        variants = result.get("variant_records", [])
        if isinstance(variants, list):
            records.extend(item for item in variants if isinstance(item, dict))
    return records
