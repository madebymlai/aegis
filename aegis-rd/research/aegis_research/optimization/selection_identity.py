from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from research.aegis_research.candidates.records import canonical_value
from research.aegis_research.configuration import OptimizationConfig, RankingConfig, ReportConfig
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.continuous_replay import continuous_replay_protocol
from research.aegis_research.optimization.observation_blocks import (
    OBSERVATION_BLOCK_PROTOCOL_SCHEMA_VERSION,
    ObservationBlockAnalysis,
    observation_block_protocol,
    observation_block_ranking_protocol,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.portfolio_simulation._simulation import (
    PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
)

CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION = "continuous_selection_identity.v1"
METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION = "bounds_metric_extractors.v2"


def build_selection_identity(
    *,
    analysis: ObservationBlockAnalysis,
    preflight: OptimizationPreflight,
    optimization: OptimizationConfig,
    metric_registry: FrozenMetricRegistry,
    ranking: RankingConfig,
    report: ReportConfig,
    direction: str,
    fill_timing: str,
    data_start: Any,
) -> Mapping[str, Any]:
    """Build only the Candidate identity facts consumed by durable behavior."""
    if analysis.blocks != preflight.blocks:
        raise ValueError("execution Observation Blocks must equal preflighted blocks")
    if ranking.metric not in metric_registry:
        raise ValueError("ranking Metric must exist in the Metric registry")
    candidates = preflight.plan.candidates
    lookbacks = preflight.plan.lookbacks
    candidate_grid = [
        {
            "position": position,
            "params": _canonical_mapping(candidates.params_at(position)),
        }
        for position in range(candidates.count)
    ]
    return _canonical_mapping(
        {
            "schema_version": CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION,
            "trial_lineage": {
                "search": optimization.search,
                "random_subset": optimization.random_subset,
                "seed": optimization.seed,
                "candidate_grid": candidate_grid,
            },
            "warmup": _warmup_identity(preflight, data_start=data_start),
            "scored_interval": {
                "start": lookbacks.scored_start,
                "end": len(analysis.blocks.index),
                "end_exclusive": True,
            },
            "replay_protocol": continuous_replay_protocol(
                fill_timing=fill_timing,
                direction=direction,
                scored_start=lookbacks.scored_start,
                sim_end=len(analysis.blocks.index),
            ),
            "observation_block_protocol": observation_block_protocol(analysis.blocks),
            "metric_protocol": _metric_protocol(metric_registry),
            "metric_inputs": {
                "freq": report.freq,
                "periods_per_year": report.periods_per_year,
                "year_freq": report.year_freq,
            },
            "ranking": observation_block_ranking_protocol(
                metric_registry.get(ranking.metric), min_trades=ranking.min_trades
            ),
        }
    )


def validate_selection_identity(identity: Mapping[str, Any]) -> None:
    if identity.get("schema_version") != CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION:
        raise ValueError("unsupported continuous selection identity schema_version")
    expected_versions = {
        "replay_protocol": PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
        "observation_block_protocol": OBSERVATION_BLOCK_PROTOCOL_SCHEMA_VERSION,
        "metric_protocol": METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION,
    }
    for field, expected_version in expected_versions.items():
        value = identity.get(field)
        if not isinstance(value, Mapping) or value.get("schema_version") != expected_version:
            raise ValueError(f"continuous selection identity has invalid {field}")
    for field in ("trial_lineage", "warmup", "scored_interval", "metric_inputs", "ranking"):
        if not isinstance(identity.get(field), Mapping):
            raise TypeError(f"continuous selection identity requires {field}")


def _warmup_identity(preflight: OptimizationPreflight, *, data_start: Any) -> dict[str, Any]:
    candidates = preflight.plan.candidates
    lookbacks = preflight.plan.lookbacks
    records = []
    maximum_drivers: list[dict[str, Any]] = []
    for position, component_lookbacks in enumerate(lookbacks.by_candidate):
        candidate_maximum = lookbacks.candidate_warmup_bars[position]
        params = _canonical_mapping(candidates.params_at(position))
        canonical_lookbacks = {
            str(component): int(bars) for component, bars in sorted(component_lookbacks.items())
        }
        records.append(
            {
                "candidate_position": position,
                "params": params,
                "component_lookbacks": canonical_lookbacks,
                "candidate_maximum": candidate_maximum,
            }
        )
        if candidate_maximum == lookbacks.resolved_warmup_bars:
            maximum_drivers.extend(
                {
                    "candidate_position": position,
                    "params": params,
                    "component": component,
                    "lookback_bars": bars,
                }
                for component, bars in canonical_lookbacks.items()
                if bars == lookbacks.resolved_warmup_bars
            )
    return {
        "data_start": canonical_value(data_start),
        "candidates": records,
        "resolved_warmup_bars": lookbacks.resolved_warmup_bars,
        "maximum_drivers": maximum_drivers,
        "scored_start": lookbacks.scored_start,
        "scored_rows": len(preflight.blocks.index) - lookbacks.scored_start,
    }


def _metric_protocol(registry: FrozenMetricRegistry) -> dict[str, Any]:
    return {
        "schema_version": METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION,
        "registry_fingerprint": registry.fingerprint,
        "candidate_vector_contract": "non_scalar_canonical_candidate_series.v1",
        "extractors": {
            metric_id: {
                "kind": (
                    "native_full_portfolio"
                    if definition.source_type == "vbt_stats"
                    else "canonical_full_path_primitives"
                ),
                "source_type": definition.source_type,
                "contract_version": registry.extractors[metric_id].contract_version,
                "boundary_semantics": definition.boundary_semantics,
                "scale": registry.extractors[metric_id].scale,
                "absolute": registry.extractors[metric_id].abs_,
            }
            for metric_id, definition in registry.definitions.items()
        },
    }


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): canonical_value(value[key]) for key in sorted(value)}


__all__ = ["build_selection_identity", "validate_selection_identity"]
