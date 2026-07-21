"""VBT-native observational analysis of unchanged continuous Candidate paths."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import ExtractorSpec, MetricDefinition
from research.aegis_research.metrics.range_extractors import (
    FullPathPrimitives,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.candidate_paths import DevelopmentPaths
from research.aegis_research.optimization.candidate_validity import Verdicts
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)

type CandidateMetricVector = pd.Series
BoundsMetricExtractor = Callable[..., CandidateMetricVector]


class ObservationBlockError(ValueError):
    """The Observation Block or bounds-aware Metric contract is invalid."""


@dataclass(frozen=True)
class ObservationBlocks:
    """Validated Aegis policy resolved into VBT-representable half-open ranges."""

    index: pd.Index
    bounds: tuple[tuple[int, int], ...]
    labels: tuple[str, ...]

    @classmethod
    def from_bounds(
        cls,
        index: pd.Index,
        bounds: Sequence[tuple[int, int]],
        *,
        labels: Sequence[str] | None = None,
    ) -> ObservationBlocks:
        resolved = tuple(bounds)
        if not resolved:
            raise ObservationBlockError("at least one Observation Block is required")
        previous_end: int | None = None
        for start, end in resolved:
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 0
                or end <= start
                or end > len(index)
            ):
                raise ObservationBlockError(
                    "Observation Block bounds must be valid integer [start, end) positions"
                )
            if previous_end is not None and start != previous_end:
                raise ObservationBlockError(
                    "Observation Blocks must be contiguous and non-overlapping"
                )
            previous_end = end
        block_labels = (
            tuple(labels)
            if labels is not None
            else tuple(f"block-{position:03d}" for position in range(len(resolved)))
        )
        if len(block_labels) != len(resolved) or len(set(block_labels)) != len(block_labels):
            raise ObservationBlockError(
                "Observation Block labels must be unique and match the resolved bounds"
            )
        return cls(index=index, bounds=resolved, labels=block_labels)

    def splitter(self) -> vbt.Splitter:
        return vbt.Splitter.from_splits(
            self.index,
            [slice(start, end) for start, end in self.bounds],
            squeeze=False,
            fix_ranges=True,
            split_labels=pd.Index(self.labels, name="observation_block"),
            set_labels=pd.Index(["observation"], name="set"),
        )


@dataclass(frozen=True)
class ObservationBlockAnalysis:
    """Raw block Metrics, ranking ranks, and the fixed representative roles."""

    blocks: ObservationBlocks
    metric_matrices: Mapping[str, pd.DataFrame]
    ranking_ranks: pd.DataFrame
    result: OptimizationResult


def apply_metric_to_blocks(
    blocks: ObservationBlocks,
    full_portfolio: Any,
    extractor: BoundsMetricExtractor,
    candidate_index: pd.Index,
) -> pd.DataFrame:
    """Apply one registered Metric to bounds without slicing the Portfolio."""

    def metric_for_bounds(bounds: tuple[int, int], portfolio: Any) -> pd.Series:
        start, end = bounds
        result = extractor(portfolio, sim_start=start, sim_end=end)
        return _candidate_metric_vector(result, candidate_index)

    result = blocks.splitter().apply(
        metric_for_bounds,
        vbt.Rep("bounds"),
        full_portfolio,
        attach_bounds=True,
        right_inclusive=False,
        iteration="split_wise",
        merge_func="column_stack",
        wrap_results=True,
    )
    if not isinstance(result, pd.DataFrame) or result.ndim != 2:
        raise ObservationBlockError(
            "VBT block application must return a two-dimensional Candidate-by-block matrix"
        )
    if not result.index.equals(candidate_index):
        raise ObservationBlockError("block Metric matrix has the wrong Candidate Index")
    if result.shape != (len(candidate_index), len(blocks.bounds)):
        raise ObservationBlockError("block Metric matrix has the wrong Candidate/block shape")
    return result


def apply_registered_metric_to_blocks(
    blocks: ObservationBlocks,
    full_portfolio: Any,
    primitives: FullPathPrimitives,
    definition: MetricDefinition,
    spec: ExtractorSpec,
    report: ReportConfig,
    candidate_index: pd.Index,
) -> pd.DataFrame:
    """Apply the registry-owned native/custom extractor and transforms."""
    range_factory = spec.range_factory
    if range_factory is None:
        raise ObservationBlockError(
            f"Metric {definition.id!r} has no bounds-aware range extractor"
        )
    read_bounds = range_factory(report)
    metric_input = full_portfolio if definition.source_type == "vbt_stats" else primitives

    def extractor(value: Any, *, sim_start: int, sim_end: int) -> pd.Series:
        raw = read_bounds(value, sim_start=sim_start, sim_end=sim_end)
        if not isinstance(raw, pd.Series) or len(raw) != len(candidate_index):
            raise ObservationBlockError(
                "registered extractor must return one value per canonical Candidate"
            )
        raw_keys = [_as_key(value) for value in raw.index.tolist()]
        candidate_keys = [_as_key(value) for value in candidate_index.tolist()]
        if raw_keys != candidate_keys:
            raise ObservationBlockError(
                "registered extractor result does not match canonical Candidate order"
            )
        result = pd.Series(raw.to_numpy(), index=candidate_index, dtype="float64")
        if spec.abs_:
            result = result.abs()
        if spec.scale == "percent":
            result = result * 100.0
        return result

    return apply_metric_to_blocks(blocks, metric_input, extractor, candidate_index)


def _candidate_metric_vector(value: Any, candidate_index: pd.Index) -> pd.Series:
    if not isinstance(value, pd.Series) or value.ndim != 1:
        raise ObservationBlockError(
            "bounds-aware extractor must return a CandidateMetricVector Series"
        )
    if not value.index.equals(candidate_index):
        raise ObservationBlockError(
            "CandidateMetricVector must use the canonical Candidate Index"
        )
    return value.astype("float64")


def select_observation_block_representatives(
    metric_matrix: pd.DataFrame,
    *,
    param_names: Sequence[str],
    verdicts: Verdicts,
    full_period_metrics: pd.DataFrame,
    definition: MetricDefinition,
) -> OptimizationResult:
    """Select best/median/worst solely by deterministic mean within-block rank."""
    candidate_keys = [_as_key(value) for value in metric_matrix.index.tolist()]
    positions = [
        position
        for position, key in enumerate(candidate_keys)
        if key in verdicts.admissible
    ]
    if not positions:
        raise ObservationBlockError("no admissible Candidate survived continuous classification")
    admissible = metric_matrix.iloc[positions]
    ranks = _rank_matrix(admissible, definition)
    mean_ranks = ranks.mean(axis="columns")
    ordered_positions = sorted(
        range(len(positions)),
        key=lambda local: (float(mean_ranks.iloc[local]), positions[local]),
    )

    evaluated: list[EvaluatedCandidate] = []
    for local in ordered_positions:
        source_position = positions[local]
        key = candidate_keys[source_position]
        block_values = admissible.iloc[local]
        evaluated.append(
            EvaluatedCandidate(
                params=dict(zip(param_names, key, strict=True)),
                score=float(mean_ranks.iloc[local]),
                selection_metrics=_selection_metrics(
                    block_values, definition.id
                ),
                metrics=_full_metrics(full_period_metrics.iloc[source_position]),
            )
        )
    count = len(evaluated)
    return OptimizationResult(
        best=evaluated[0],
        median=evaluated[ceil(count / 2) - 1],
        worst=evaluated[-1],
        excluded_degenerate=verdicts.excluded_degenerate,
        excluded_invalid=verdicts.excluded_invalid,
        total_candidates=verdicts.total,
        omnibus=None,
    )


def analyze_development_paths(
    paths: DevelopmentPaths,
    blocks: ObservationBlocks,
    *,
    report: ReportConfig,
    metric_registry: FrozenMetricRegistry,
    ranking_metric: str,
) -> ObservationBlockAnalysis:
    """Apply all registered Metrics and select solely from the ranking Metric ranks."""
    if ranking_metric not in metric_registry:
        raise ObservationBlockError(
            f"ranking metric {ranking_metric!r} is not in the Metric registry"
        )
    if (
        blocks.index is not paths.replay.portfolio.wrapper.index
        and not blocks.index.equals(paths.replay.portfolio.wrapper.index)
    ):
        raise ObservationBlockError("Observation Blocks must use the continuous path index")
    if (
        blocks.bounds[0][0] != paths.replay.scored_start
        or blocks.bounds[-1][1] != paths.replay.sim_end
    ):
        raise ObservationBlockError(
            "Observation Blocks must cover the complete common scored interval"
        )
    candidate_index = pd.MultiIndex.from_tuples(
        list(paths.candidates.keys), names=list(paths.candidates.param_names)
    )
    primitives = FullPathPrimitives.from_portfolio(paths.replay.portfolio)
    matrices = {
        metric_id: apply_registered_metric_to_blocks(
            blocks,
            paths.replay.portfolio,
            primitives,
            metric_registry.get(metric_id),
            spec,
            report,
            candidate_index,
        )
        for metric_id, spec in metric_registry.extractors.items()
    }
    definition = metric_registry.get(ranking_metric)
    result = select_observation_block_representatives(
        matrices[ranking_metric],
        param_names=paths.candidates.param_names,
        verdicts=paths.verdicts,
        full_period_metrics=paths.full_period_metrics,
        definition=definition,
    )
    return ObservationBlockAnalysis(
        blocks=blocks,
        metric_matrices=matrices,
        ranking_ranks=_rank_matrix(matrices[ranking_metric], definition),
        result=result,
    )


def _rank_matrix(matrix: pd.DataFrame, definition: MetricDefinition) -> pd.DataFrame:
    return matrix.rank(
        axis="index",
        method="average",
        ascending=definition.direction == "minimize",
        na_option="bottom",
    )


def _as_key(value: Any) -> tuple[Any, ...]:
    return value if isinstance(value, tuple) else (value,)


def _selection_metrics(
    row: pd.Series, metric_id: str
) -> Mapping[Any, Mapping[str, float | None]]:
    return {
        _block_label(column): {metric_id: _optional_float(value)}
        for column, value in row.items()
    }


def _block_label(column: Any) -> Any:
    if isinstance(column, tuple):
        return column[0]
    return column


def _full_metrics(row: pd.Series) -> Mapping[str, float | None]:
    return {str(name): _optional_float(value) for name, value in row.items()}


def _optional_float(value: Any) -> float | None:
    return float(value) if pd.notna(value) and np.isfinite(value) else None


__all__ = [
    "BoundsMetricExtractor",
    "CandidateMetricVector",
    "ObservationBlockAnalysis",
    "ObservationBlockError",
    "ObservationBlocks",
    "analyze_development_paths",
    "apply_metric_to_blocks",
    "apply_registered_metric_to_blocks",
    "select_observation_block_representatives",
]
