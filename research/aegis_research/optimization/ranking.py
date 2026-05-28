"""Global, min-aware ranking of fixed-parameter candidates across splits.

Pure pandas/numpy. Replaces per-split winner selection: each candidate's
Selection-set metric is scored *across all splits* with a min-aware composite,
then three real, deployable candidates (best / median / worst) are returned.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil, isnan
from typing import Any

import pandas as pd

SPLIT_LEVEL = "split"


@dataclass(frozen=True)
class EvaluatedCandidate:
    """A fixed-parameter candidate scored globally across splits.

    ``selection_metrics`` and ``held_out_metrics`` map a split label to that
    split's metric values (``metric_id -> value``); a value is ``None`` when the
    metric was missing or NaN on that split. ``held_out_metrics`` is empty here
    and is populated later by the runner's held-out validation phase. ``metrics``
    carries every metric aggregated (mean across splits, skipping missing values).
    """

    params: Mapping[str, Any]
    score: float
    selection_metrics: Mapping[Any, Mapping[str, float | None]]
    metrics: Mapping[str, float | None]
    held_out_metrics: Mapping[Any, Mapping[str, float | None]] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizationResult:
    """Exactly three representative candidates selected by global ranking."""

    best: EvaluatedCandidate
    median: EvaluatedCandidate
    worst: EvaluatedCandidate


def select_representative_candidates(
    grid: pd.DataFrame,
    *,
    metric: str,
    min_weight: float = 0.3,
) -> OptimizationResult:
    """Rank fixed-param candidates globally and return best/median/worst.

    ``grid`` is a tidy frame with one row per (candidate, split): a MultiIndex
    carrying a ``"split"`` level plus one or more parameter levels that jointly
    identify a candidate, and one column per Selection-set metric.

    Each candidate is scored across its splits with a min-aware composite
    (higher is better)::

        score = (1 - min_weight) * mean(values) + min_weight * min(values)

    Ranking is always descending. ``best`` is rank 1, ``median`` is rank
    ``ceil(N/2)``, and ``worst`` is rank N — all real candidates. Ties keep
    candidate (parameter-sorted) order. A split whose metric is NaN/None is
    skipped; a candidate with no valid values scores NaN and ranks last.
    """
    if metric not in grid.columns:
        raise KeyError(f"ranking metric {metric!r} not present in grid columns")
    if not isinstance(grid.index, pd.MultiIndex):
        raise TypeError("grid index must be a MultiIndex with a 'split' level and param levels")
    if SPLIT_LEVEL not in grid.index.names:
        raise ValueError(f"grid index must include a {SPLIT_LEVEL!r} level; got {grid.index.names}")
    param_levels = [name for name in grid.index.names if name != SPLIT_LEVEL]
    if not param_levels:
        raise ValueError("grid index must carry at least one parameter level")

    metric_columns = list(grid.columns)
    group_level = param_levels[0] if len(param_levels) == 1 else param_levels
    candidates: list[EvaluatedCandidate] = []
    for key, sub in grid.groupby(level=group_level, sort=True):
        key_tuple = key if isinstance(key, tuple) else (key,)
        params = dict(zip(param_levels, key_tuple, strict=True))
        split_labels = sub.index.get_level_values(SPLIT_LEVEL)

        selection_metrics: dict[Any, dict[str, float | None]] = {}
        for split_label, (_, row) in zip(split_labels, sub.iterrows(), strict=True):
            selection_metrics[split_label] = {
                col: _to_optional_float(row[col]) for col in metric_columns
            }

        aggregated = {
            col: _mean([selection_metrics[s][col] for s in selection_metrics])
            for col in metric_columns
        }
        score = _min_aware_score(
            (selection_metrics[s][metric] for s in selection_metrics), min_weight
        )
        candidates.append(
            EvaluatedCandidate(
                params=params,
                score=score,
                selection_metrics=selection_metrics,
                metrics=aggregated,
            )
        )

    ranked = sorted(candidates, key=_rank_key)
    n = len(ranked)
    return OptimizationResult(
        best=ranked[0],
        median=ranked[ceil(n / 2) - 1],
        worst=ranked[n - 1],
    )


def _rank_key(candidate: EvaluatedCandidate) -> tuple[int, float]:
    score = candidate.score
    if isnan(score):
        return (1, 0.0)  # NaN scores rank last, regardless of value
    return (0, -score)  # descending: highest score first


def _min_aware_score(values: Iterable[float | None], min_weight: float) -> float:
    valid = [v for v in values if v is not None]
    if not valid:
        return float("nan")
    mean = sum(valid) / len(valid)
    return (1.0 - min_weight) * mean + min_weight * min(valid)


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if isnan(number) else number
