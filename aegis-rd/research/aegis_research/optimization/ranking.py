"""Global, empirical-Bayes ranking of fixed-parameter candidates across splits.

Consumes the Candidate Grid's mapping read surface directly. Exclusion rules
live in ``candidate_validity``; ranking consumes the verdict without re-deriving
any exclusion logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil, isnan, sqrt
from statistics import median, pvariance, stdev
from typing import Any, NamedTuple

from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_validity import Verdicts

# Reliability floor for the empirical-Bayes between-candidate variance. When the
# between-candidate spread does not exceed the estimated noise (a noise-dominated
# field), ``s2_between`` is held at this small fraction of the median within-
# candidate noise rather than zero, so ranking still favours reliability instead
# of collapsing every candidate onto the grand mean. It is a numerical guard, not
# a tuning knob: any value in a wide range leaves the ranking order unchanged.
_RELIABILITY_FLOOR = 1e-6


@dataclass(frozen=True)
class EvaluatedCandidate:
    """A fixed-parameter candidate scored globally across splits.

    ``selection_metrics`` and ``held_out_metrics`` map a split label to that
    split's metric values (``metric_id -> value``); a value is ``None`` when the
    metric was missing or NaN on that split. ``held_out_metrics`` is empty here
    and is populated later by the runner's held-out validation phase. ``metrics``
    carries every metric aggregated (mean across splits, skipping missing values).

    ``score`` is the candidate's empirical-Bayes shrunk ranking score (see
    :func:`select_representative_candidates`), not a raw per-split mean.
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

    ``non_executable_rows`` is the seam cost of the Split structure: the
    number of rebalance rows held at calendar seams across all (split, set)
    windows, computed from the split geometry and the loaded-data calendar
    alone — independent of which candidates ran or how the sweep was chunked.
    A value of zero means the split method produced contiguous windows; a
    positive value records the structural execution-footprint cost of
    non-contiguous splits (e.g. purged k-fold).
    """

    best: EvaluatedCandidate
    median: EvaluatedCandidate
    worst: EvaluatedCandidate
    excluded_degenerate: int = 0
    excluded_invalid: int = 0
    total_candidates: int = 0
    non_executable_rows: int = 0


class _RawCandidate(NamedTuple):
    """A candidate carried through the two-pass ranking with its raw statistics."""

    params: Mapping[str, Any]
    selection_metrics: Mapping[Any, Mapping[str, float | None]]
    metrics: Mapping[str, float | None]
    raw: float
    se: float | None


def select_representative_candidates(
    grid: CandidateGrid,
    verdicts: Verdicts,
    *,
    metric: str,
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

    Candidates are scored by **empirical-Bayes shrinkage across the grid**
    (Efron-Morris / James-Stein), higher is better. Each candidate's raw score is
    the mean of its ranking metric across splits; that raw score is then shrunk
    toward the grand mean by a factor set by the candidate's *across-split*
    reliability (see :func:`_empirical_bayes_scores`). A candidate whose metric
    swings wildly across splits — e.g. one lucky spike carrying the mean — has a
    large standard error and is pulled hard toward the field, self-deflating the
    winner's curse; a steady, consistently high (convex) candidate keeps its raw
    score. When every candidate is perfectly consistent (zero across-split spread)
    the shrinkage vanishes and ranking reduces to the raw per-split mean.

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
    raw_candidates: list[_RawCandidate] = []
    for key_tuple, split_metrics in grid.by_candidate():
        if key_tuple not in admissible:
            continue
        params = dict(zip(param_levels, key_tuple, strict=True))
        aggregated = {
            col: _mean([split_metrics[s][col] for s in split_metrics])
            for col in metric_ids
        }
        # Admissible candidates carry at least one finite ranking score by verdict,
        # so the None-skipping aggregate of the ranking metric is finite here; reuse
        # it as the raw score rather than recomputing the same mean.
        raw = aggregated[metric]
        assert raw is not None
        ranking_values = [
            value
            for s in split_metrics
            if (value := split_metrics[s][metric]) is not None
        ]
        raw_candidates.append(
            _RawCandidate(params, split_metrics, aggregated, raw, _candidate_se(ranking_values))
        )

    if not raw_candidates:
        raise ValueError(
            f"no admissible candidate survived; all {verdicts.total} candidates "
            f"were excluded by the validity verdict (invalid={verdicts.excluded_invalid}, "
            f"non_trading={len(verdicts.non_trading)}, under_traded={len(verdicts.under_traded)})"
        )

    scores = _empirical_bayes_scores(
        [c.raw for c in raw_candidates], [c.se for c in raw_candidates]
    )
    candidates = [
        EvaluatedCandidate(
            params=c.params,
            score=score,
            selection_metrics=c.selection_metrics,
            metrics=c.metrics,
        )
        for c, score in zip(raw_candidates, scores, strict=True)
    ]
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
    accidentally outranking real values in descending sort. Equal scores keep
    parameter-sorted order because ``sorted`` is stable and the candidate list is
    built in the grid's parameter-sorted iteration order.
    """
    score = candidate.score
    if isnan(score):
        return (1, 0.0)
    return (0, -score)


def _candidate_se(values: list[float]) -> float | None:
    """Across-split standard error of a candidate's ranking metric.

    ``None`` when fewer than two finite splits exist (no measurable spread);
    those candidates are treated as maximally unreliable during shrinkage.
    """
    if len(values) < 2:
        return None
    return stdev(values) / sqrt(len(values))


def _empirical_bayes_scores(raws: list[float], ses: list[float | None]) -> list[float]:
    """Empirical-Bayes posterior means shrinking each raw score toward the grand mean.

    ::

        shrunk = grand + [s2_between / (s2_between + se**2)] * (raw - grand)

    The pull is set by each candidate's across-split reliability: a large ``se``
    (a metric driven by one lucky split) shrinks hard toward the field, undoing
    the winner's curse without penalising a consistently high candidate.
    ``s2_between`` is the method-of-moments between-candidate variance,
    ``Var(raw) - noise``, where ``noise`` is the *median* squared standard error
    across candidates — the within-candidate noise on each raw mean. Taking the
    median rather than the mean keeps a single wildly-varying candidate from
    inflating the noise term and flattening the whole ranking. When every
    candidate is perfectly consistent (all ``se`` zero) the shrinkage factor is
    one and ranking reduces to the raw per-split mean.
    """
    grand = sum(raws) / len(raws)
    known = [s for s in ses if s is not None]
    # A single-finite-split candidate has no measurable spread; treat it as
    # maximally unreliable (the largest observed se) so it shrinks hardest.
    fallback = max(known) if known else 0.0
    se2 = [(fallback if s is None else s) ** 2 for s in ses]
    within = median(se2)
    between = pvariance(raws) if len(raws) > 1 else 0.0
    s2 = max(between - within, _RELIABILITY_FLOOR * within)
    return [
        grand + (s2 / (s2 + v) if s2 + v > 0.0 else 1.0) * (raw - grand)
        for raw, v in zip(raws, se2, strict=True)
    ]


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None
