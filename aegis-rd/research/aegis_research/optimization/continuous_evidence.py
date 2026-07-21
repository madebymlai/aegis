"""Canonical Evidence and identity for continuous Candidate selection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.configuration import (
    OptimizationConfig,
    RankingConfig,
    ReportConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_evidence import canonical_value
from research.aegis_research.optimization.candidate_validity import Verdicts
from research.aegis_research.optimization.continuous_replay import (
    continuous_replay_protocol,
)
from research.aegis_research.optimization.observation_blocks import (
    OBSERVATION_BLOCK_PROTOCOL_SCHEMA_VERSION,
    ObservationBlockAnalysis,
    ObservationBlocks,
    observation_block_protocol,
    observation_block_ranking_protocol,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.optimization.window_evaluation._simulation import (
    PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
)

CONTINUOUS_SELECTION_EVIDENCE_SCHEMA_VERSION = "continuous_selection_evidence.v1"
CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION = "continuous_selection_identity.v1"
MATRIX_EVIDENCE_SCHEMA_VERSION = "candidate_block_matrix.v1"
METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION = "bounds_metric_extractors.v1"


@dataclass(frozen=True)
class ContinuousEvidence:
    """Execution Evidence and the exact identity shared by published Candidates."""

    execution: Mapping[str, Any]
    selection_identity: Mapping[str, Any]


def build_continuous_evidence(
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
) -> ContinuousEvidence:
    """Serialize the exact preflighted continuous replay and observational ranking."""
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
    candidate_positions = {key: position for position, key in enumerate(candidates.keys)}
    warmup = _warmup_evidence(preflight, data_start=data_start)
    block_protocol = observation_block_protocol(analysis.blocks)
    replay_protocol = continuous_replay_protocol(
        fill_timing=fill_timing,
        direction=direction,
        scored_start=lookbacks.scored_start,
        sim_end=len(analysis.blocks.index),
    )
    metric_protocol = _metric_protocol(metric_registry)
    ranking_definition = metric_registry.get(ranking.metric)
    selection_identity = _canonical_mapping(
        {
            "schema_version": CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION,
            "trial_lineage": {
                "search": optimization.search,
                "random_subset": optimization.random_subset,
                "seed": optimization.seed,
                "candidate_grid": candidate_grid,
            },
            "warmup": warmup,
            "scored_interval": {
                "start": lookbacks.scored_start,
                "end": len(analysis.blocks.index),
                "end_exclusive": True,
            },
            "replay_protocol": replay_protocol,
            "observation_block_protocol": block_protocol,
            "metric_protocol": metric_protocol,
            "metric_inputs": {
                "freq": report.freq,
                "periods_per_year": report.periods_per_year,
                "year_freq": report.year_freq,
            },
            "ranking": observation_block_ranking_protocol(
                ranking_definition, min_trades=ranking.min_trades
            ),
        }
    )
    execution = _canonical_mapping(
        {
            "schema_version": CONTINUOUS_SELECTION_EVIDENCE_SCHEMA_VERSION,
            "history_role": "development_selection",
            "selection_identity": selection_identity,
            "warmup": warmup,
            "raw_metric_matrices": {
                metric_id: matrix_to_evidence(matrix)
                for metric_id, matrix in sorted(analysis.metric_matrices.items())
            },
            "within_block_rank_matrix": matrix_to_evidence(analysis.ranking_ranks),
            "mean_ranks": _mean_rank_evidence(
                analysis.ranking_ranks,
                candidate_positions=candidate_positions,
                candidate_grid=candidate_grid,
            ),
            "complete_period_metrics": table_to_evidence(analysis.full_period_metrics),
            "representatives": _representative_evidence(analysis),
            "candidate_accounting": {
                "total": analysis.result.total_candidates,
                "excluded_invalid": analysis.result.excluded_invalid,
                "excluded_degenerate": analysis.result.excluded_degenerate,
                "verdicts": [
                    {
                        "candidate_position": position,
                        "params": candidate_grid[position]["params"],
                        "verdict": _candidate_verdict(key, analysis.verdicts),
                    }
                    for position, key in enumerate(candidates.keys)
                ],
            },
        }
    )
    return ContinuousEvidence(
        execution=execution,
        selection_identity=selection_identity,
    )


def matrix_to_evidence(matrix: pd.DataFrame) -> dict[str, Any]:
    """Encode a stable two-dimensional Candidate-by-Observation-Block matrix."""
    if not isinstance(matrix.index, pd.MultiIndex):
        raise TypeError("Candidate matrix index must be a MultiIndex")
    if not isinstance(matrix.columns, pd.MultiIndex):
        raise TypeError("Observation Block matrix columns must be a MultiIndex")
    return {
        "schema_version": MATRIX_EVIDENCE_SCHEMA_VERSION,
        "orientation": "candidate_by_observation_block",
        "candidate_index": {
            "names": list(matrix.index.names),
            "values": [list(map(canonical_value, _as_tuple(value))) for value in matrix.index],
        },
        "observation_blocks": [
            {"label": str(label), "start": int(start), "end": int(end)}
            for label, start, end in matrix.columns.tolist()
        ],
        "values": [[_optional_float(value) for value in row] for row in matrix.to_numpy().tolist()],
    }


def matrix_from_evidence(payload: Mapping[str, Any]) -> pd.DataFrame:
    """Decode and validate a canonical Candidate-by-Observation-Block matrix."""
    if payload.get("schema_version") != MATRIX_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported Candidate block matrix schema_version")
    if payload.get("orientation") != "candidate_by_observation_block":
        raise ValueError("unsupported Candidate block matrix orientation")
    index_payload = payload["candidate_index"]
    index = pd.MultiIndex.from_tuples(
        [tuple(_restore_canonical(item) for item in value) for value in index_payload["values"]],
        names=index_payload["names"],
    )
    columns = pd.MultiIndex.from_tuples(
        [
            (block["label"], int(block["start"]), int(block["end"]))
            for block in payload["observation_blocks"]
        ],
        names=["observation_block", "start", "end"],
    )
    result = pd.DataFrame(payload["values"], index=index, columns=columns, dtype="float64")
    if result.shape != (len(index), len(columns)):
        raise ValueError("Candidate block matrix values do not match declared shape")
    return result


def table_to_evidence(table: pd.DataFrame) -> dict[str, Any]:
    """Encode complete-period Metric values in canonical Candidate-row orientation."""
    if not isinstance(table.index, pd.MultiIndex):
        raise TypeError("complete-period Metric table index must be a MultiIndex")
    return {
        "schema_version": "candidate_metric_table.v1",
        "orientation": "candidate_by_metric",
        "candidate_index": {
            "names": list(table.index.names),
            "values": [list(map(canonical_value, _as_tuple(value))) for value in table.index],
        },
        "metrics": [str(column) for column in table.columns],
        "values": [[_optional_float(value) for value in row] for row in table.to_numpy().tolist()],
    }


def observation_blocks_from_evidence(
    index: pd.Index, execution: Mapping[str, Any]
) -> ObservationBlocks:
    """Reproduce labeled half-open bounds from published execution Evidence."""
    identity = execution.get("selection_identity")
    if not isinstance(identity, Mapping):
        raise TypeError("continuous Evidence has no selection identity")
    protocol = identity.get("observation_block_protocol")
    if not isinstance(protocol, Mapping):
        raise TypeError("continuous Evidence has no Observation Block protocol")
    blocks = protocol.get("bounds")
    if not isinstance(blocks, list):
        raise TypeError("Observation Block Evidence has no bounds")
    return ObservationBlocks.from_bounds(
        index,
        [(int(block["start"]), int(block["end"])) for block in blocks],
        labels=[str(block["label"]) for block in blocks],
    )


def validate_selection_identity(identity: Mapping[str, Any]) -> None:
    """Reject stale or structurally incomplete continuous-selection identity."""
    if identity.get("schema_version") != CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION:
        raise ValueError("unsupported continuous selection identity schema_version")
    expected_nested_versions = {
        "replay_protocol": PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
        "observation_block_protocol": OBSERVATION_BLOCK_PROTOCOL_SCHEMA_VERSION,
        "metric_protocol": METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION,
    }
    for field, expected_version in expected_nested_versions.items():
        value = identity.get(field)
        if not isinstance(value, Mapping) or value.get("schema_version") != expected_version:
            raise ValueError(f"continuous selection identity has invalid {field}")
    for field in (
        "trial_lineage",
        "warmup",
        "scored_interval",
        "metric_inputs",
        "ranking",
    ):
        if not isinstance(identity.get(field), Mapping):
            raise TypeError(f"continuous selection identity requires {field}")


def _warmup_evidence(preflight: OptimizationPreflight, *, data_start: Any) -> dict[str, Any]:
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


def _mean_rank_evidence(
    ranks: pd.DataFrame,
    *,
    candidate_positions: dict[tuple[Any, ...], int],
    candidate_grid: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key, value in zip(ranks.index.tolist(), ranks.mean(axis="columns").tolist(), strict=True):
        try:
            position = candidate_positions[_as_tuple(key)]
        except KeyError as error:
            raise ValueError("rank matrix contains an unknown Candidate identity") from error
        records.append(
            {
                "candidate_position": position,
                "params": candidate_grid[position]["params"],
                "value": _optional_float(value),
            }
        )
    return records


def _candidate_verdict(key: tuple[Any, ...], verdicts: Verdicts) -> str:
    if key in verdicts.invalid:
        return "invalid"
    if key in verdicts.non_trading:
        return "non_trading"
    if key in verdicts.under_traded:
        return "under_traded"
    if key in verdicts.valid:
        return "valid"
    raise ValueError("Candidate verdict partition is incomplete")


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
                "boundary_semantics": definition.boundary_semantics,
                "scale": registry.extractors[metric_id].scale,
                "absolute": registry.extractors[metric_id].abs_,
            }
            for metric_id, definition in registry.definitions.items()
        },
    }


def _representative_evidence(analysis: ObservationBlockAnalysis) -> list[dict[str, Any]]:
    return [
        {
            "role": role,
            "ordinal_rank": ordinal,
            "params": _canonical_mapping(candidate.params),
            "mean_rank": _optional_float(candidate.score),
            "observation_block_metrics": _block_metrics(candidate.observation_block_metrics),
            "complete_period_metrics": _metric_map(candidate.metrics),
        }
        for ordinal, (role, candidate) in enumerate(
            zip(
                ("best", "median", "worst"),
                (analysis.result.best, analysis.result.median, analysis.result.worst),
                strict=True,
            ),
            start=1,
        )
    ]


def _block_metrics(
    metrics: Mapping[Any, Mapping[str, float | None]],
) -> dict[str, dict[str, float | None]]:
    return {
        str(block): _metric_map(values)
        for block, values in sorted(metrics.items(), key=lambda item: str(item[0]))
    }


def _metric_map(values: Mapping[str, float | None]) -> dict[str, float | None]:
    return {str(metric): _optional_float(values[metric]) for metric in sorted(values)}


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): canonical_value(value[key]) for key in sorted(value)}


def _optional_float(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)


def _as_tuple(value: Any) -> tuple[Any, ...]:
    return value if isinstance(value, tuple) else (value,)


def _restore_canonical(value: Any) -> Any:
    """Restore hashable Candidate coordinate values from canonical Evidence."""
    if isinstance(value, list):
        return tuple(_restore_canonical(item) for item in value)
    if not isinstance(value, Mapping):
        return value
    kind = value.get("kind")
    if kind == "timestamp":
        return pd.Timestamp(value["value"])
    if kind == "timedelta":
        return pd.Timedelta(value["value"])
    if kind == "nan":
        return float("nan")
    if kind == "infinity":
        return float("inf") if int(value["sign"]) > 0 else float("-inf")
    if kind == "enum":
        return _restore_canonical(value["value"])
    if kind == "repr":
        return str(value["value"])
    return tuple((str(key), _restore_canonical(item)) for key, item in sorted(value.items()))


__all__ = [
    "CONTINUOUS_SELECTION_EVIDENCE_SCHEMA_VERSION",
    "CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION",
    "ContinuousEvidence",
    "build_continuous_evidence",
    "matrix_from_evidence",
    "matrix_to_evidence",
    "observation_blocks_from_evidence",
    "validate_selection_identity",
]
