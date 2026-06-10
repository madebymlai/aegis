"""Global, min-aware ranking of fixed-parameter candidates across splits.

Consumes the Candidate Grid's mapping read surface directly. Exclusion rules
live in ``candidate_validity``; ranking consumes the verdict without re-deriving
any exclusion logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil, isnan
from typing import Any

from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_validity import Verdicts


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

    ``excluded_degenerate`` counts the candidates excluded before slot selection
    by the validity verdict: Invalid (indicator output entirely non-finite over
    full history), non-trading (no finite ranking score across any split), and
    under-traded (closed-trade count below the min-trades floor).
    best/median/worst are always drawn from the admissible (valid) population;
    this field tells consumers how much of the sampled grid was dead or
    under-traded.

    ``excluded_invalid`` is the subset of ``excluded_degenerate`` that was
    excluded because an indicator output was entirely non-finite over the *full
    series* (lookback exceeds the entire available history). It lets consumers
    distinguish misconfiguration from mere poor performance; the nesting
    invariant ``excluded_invalid <= excluded_degenerate <= total_candidates``
    holds by construction (the Verdicts value object owns the partition).

    ``total_candidates`` is the *exact* number of Candidates that entered
    ranking (the size of the classified set), never a preflight pre-sampling
    estimate. By the time ranking runs the verdict is materialised, so the count
    is authoritative by construction. It lets consumers report the
    researched/total terminal ratio.
    """

    best: EvaluatedCandidate
    median: EvaluatedCandidate
    worst: EvaluatedCandidate
    excluded_degenerate: int = 0
    excluded_invalid: int = 0
    total_candidates: int = 0


def select_representative_candidates(
    grid: CandidateGrid,
    verdicts: Verdicts,
    *,
    metric: str,
    min_weight: float = 0.3,
) -> OptimizationResult:
    """Rank admissible (valid) candidates globally and return best/median/worst.

    ``grid`` is a CandidateGrid whose ``by_candidate()`` iterator yields
    per-Candidate ``(CandidateKey, split → metric_id → float-or-None)`` mappings
    with NaN already normalized to None. Iteration order is parameter-sorted and
    deterministic — ranking tie-stability rests on this contract.

    ``verdicts`` is a pre-computed ``Verdicts`` partition from
    ``candidate_validity.classify_candidates``. Only ``verdicts.valid``
    candidates are scored; excluded candidates (invalid, non_trading,
    under_traded) can never occupy a representative role.

    Each candidate is scored across its splits with a min-aware composite
    (higher is better)::

        score = (1 - min_weight) * mean(values) + min_weight * min(values)

    best/median/worst are ranked among the ``N`` admissible survivors:
    ``best`` is rank 1, ``median`` is rank ``ceil(N/2)``, and ``worst`` is rank N
    — all real, valid candidates. Ranking is always descending; ties keep
    candidate (parameter-sorted) order. A split whose metric is NaN/None is
    skipped. Raises ``ValueError`` when no candidate survives.

    ``OptimizationResult`` is constructed exactly once with counts copied
    straight from the verdict: no post-hoc patch is needed.
    """
    metric_ids = grid.metric_ids
    if metric not in metric_ids:
        raise KeyError(f"ranking metric {metric!r} not present in grid columns")

    param_levels = grid.param_levels
    admissible = verdicts.admissible
    candidates: list[EvaluatedCandidate] = []
    for key_tuple, split_metrics in grid.by_candidate():
        if key_tuple not in admissible:
            continue
        params = dict(zip(param_levels, key_tuple, strict=True))

        aggregated = {
            col: _mean([split_metrics[s][col] for s in split_metrics])
            for col in metric_ids
        }
        score = _min_aware_score(
            (split_metrics[s][metric] for s in split_metrics), min_weight
        )
        candidates.append(
            EvaluatedCandidate(
                params=params,
                score=score,
                selection_metrics=split_metrics,
                metrics=aggregated,
            )
        )

    if not candidates:
        raise ValueError(
            f"no admissible candidate survived; all {verdicts.total} candidates "
            f"were excluded by the validity verdict (invalid={verdicts.excluded_invalid}, "
            f"non_trading={len(verdicts.non_trading)}, under_traded={len(verdicts.under_traded)})"
        )
    ranked = sorted(candidates, key=_rank_key)
    n = len(ranked)
    return OptimizationResult(
        best=ranked[0],
        median=ranked[ceil(n / 2) - 1],
        worst=ranked[n - 1],
        excluded_degenerate=verdicts.excluded_degenerate,
        excluded_invalid=verdicts.excluded_invalid,
        total_candidates=verdicts.total,
    )


def _rank_key(candidate: EvaluatedCandidate) -> tuple[int, float]:
    """Sort key: highest score first; NaN sinks to the bottom.

    NaN is a defensive safety net — admissible candidates (the only ones scored)
    should never carry a NaN score — but the guard keeps an unexpected NaN from
    accidentally outranking real values in descending sort.
    """
    score = candidate.score
    if isnan(score):
        return (1, 0.0)
    return (0, -score)


def _min_aware_score(values: Iterable[float | None], min_weight: float) -> float:
    valid = [v for v in values if v is not None]
    if not valid:
        return float("nan")
    mean = sum(valid) / len(valid)
    return (1.0 - min_weight) * mean + min_weight * min(valid)


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def optional_float(value: Any) -> float | None:
    """Normalize a scalar to float or None, converting NaN to None.

    Kept here as a utility for the runner's held-out attachment path, which
    processes a raw DataFrame for held-out scores.
    """
    if value is None:
        return None
    number = float(value)
    return None if isnan(number) else number
