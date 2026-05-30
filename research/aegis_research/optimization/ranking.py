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

# Grid column carrying the per-split closed-trade count (``pf.exit_trades.count()``
# via the central metric catalog). The min-trades floor reads it; the runner always
# emits it as one of the Selection-set metric columns.
TRADES_METRIC = "total_trades"


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
    """Exactly three representative candidates selected by global ranking.

    ``excluded_degenerate`` counts the candidates dropped before slot selection
    because they were not trustworthy enough to represent the grid: either they
    had no finite ranking score (non-trading / all-NaN across splits) or they
    failed the minimum-trades floor (too few closed trades per split to be more
    than in-sample luck). best/median/worst are always drawn from the surviving
    population; this field tells consumers how much of the sampled grid was dead
    or under-traded.

    ``excluded_invalid`` is the subset of ``excluded_degenerate`` that was dropped
    because an indicator output was entirely non-finite over the *full series*
    (lookback exceeds the entire available history) — i.e. *misconfigured* rather
    than merely *poor / non-trading*. It lets consumers tell those apart;
    ``excluded_invalid <= excluded_degenerate`` always holds. The runner sets it
    (the ranking layer only sees scores, not indicator history), so it defaults
    to 0 here.

    ``total_candidates`` is the *exact* number of Candidates that entered ranking
    (the size of the ranked set), never a preflight pre-sampling estimate. By the
    time ranking runs the sample is materialised, so the count is exact by
    construction. It lets consumers report the researched/total terminal ratio;
    the nesting invariant ``excluded_invalid <= excluded_degenerate <=
    total_candidates`` always holds.
    """

    best: EvaluatedCandidate
    median: EvaluatedCandidate
    worst: EvaluatedCandidate
    excluded_degenerate: int = 0
    excluded_invalid: int = 0
    total_candidates: int = 0


def select_representative_candidates(
    grid: pd.DataFrame,
    *,
    metric: str,
    min_weight: float = 0.3,
    min_trades: int = 0,
    trades_metric: str = TRADES_METRIC,
) -> OptimizationResult:
    """Rank fixed-param candidates globally and return best/median/worst.

    ``grid`` is a tidy frame with one row per (candidate, split): a MultiIndex
    carrying a ``"split"`` level plus one or more parameter levels that jointly
    identify a candidate, and one column per Selection-set metric.

    Each candidate is scored across its splits with a min-aware composite
    (higher is better)::

        score = (1 - min_weight) * mean(values) + min_weight * min(values)

    Two classes of candidate are excluded *before* slot selection so they can
    never occupy a representative role, and both are counted in
    ``OptimizationResult.excluded_degenerate``:

    * **Non-trading** — no finite score (NaN across every split).
    * **Under-traded** — when ``min_trades > 0``, a candidate whose closed-trade
      count (``trades_metric`` column) falls below ``min_trades`` on any split it
      traded. This stops a candidate from winning on a handful of lucky in-sample
      trades (a Sharpe over 2-5 trades is mostly noise). The floor is per-split:
      the candidate must clear ``min_trades`` on the *thinnest* split it scored.

    best/median/worst are then ranked among the remaining ``N`` survivors:
    ``best`` is rank 1, ``median`` is rank ``ceil(N/2)``, and ``worst`` is rank N
    — all real, sufficiently-traded candidates. Ranking is always descending;
    ties keep candidate (parameter-sorted) order. A split whose metric is
    NaN/None is skipped. Raises ``ValueError`` when no candidate survives.
    """
    if metric not in grid.columns:
        raise KeyError(f"ranking metric {metric!r} not present in grid columns")
    if min_trades > 0 and trades_metric not in grid.columns:
        raise KeyError(
            f"min_trades floor requires the {trades_metric!r} column in the grid; "
            f"got columns {list(grid.columns)}"
        )
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
    trading = [
        candidate
        for candidate in ranked
        if not isnan(candidate.score)
        and _meets_trade_floor(candidate, trades_metric, min_trades)
    ]
    if not trading:
        raise ValueError(
            f"no candidate produced a finite ranking score on {metric!r} that cleared "
            f"the min_trades={min_trades} closed-trade floor; all {len(ranked)} candidates "
            f"were degenerate (non-trading / NaN-scored / under-traded)"
        )
    n = len(trading)
    return OptimizationResult(
        best=trading[0],
        median=trading[ceil(n / 2) - 1],
        worst=trading[n - 1],
        excluded_degenerate=len(ranked) - n,
        total_candidates=len(ranked),
    )


def _meets_trade_floor(
    candidate: EvaluatedCandidate, trades_metric: str, min_trades: int
) -> bool:
    """Whether a candidate cleared the per-split closed-trade floor.

    The floor is disabled when ``min_trades <= 0``. Otherwise the candidate must
    have closed at least ``min_trades`` trades on the *thinnest* split it actually
    scored: splits where the candidate did not trade (``trades_metric`` is None)
    are skipped, mirroring how the min-aware score skips NaN-metric splits. A
    candidate with no recorded trade count anywhere fails the floor.
    """
    if min_trades <= 0:
        return True
    counts = [
        split_metrics.get(trades_metric)
        for split_metrics in candidate.selection_metrics.values()
    ]
    traded = [count for count in counts if count is not None]
    return bool(traded) and min(traded) >= min_trades


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
