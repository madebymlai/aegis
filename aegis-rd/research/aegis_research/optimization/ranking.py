"""Global, empirical-Bayes ranking of fixed-parameter candidates across splits.

Consumes the Candidate Grid's mapping read surface directly. Exclusion rules
live in ``candidate_validity``; ranking consumes the verdict without re-deriving
any exclusion logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from math import ceil, isnan, sqrt
from statistics import pvariance, stdev
from typing import Any, NamedTuple

from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_validity import Verdicts


class ShrinkTarget(Enum):
    """Where empirical-Bayes shrinkage pulls each candidate's raw score.

    ``GRAND_MEAN`` — the random-effects (precision-weighted) mean of the field:
    the exchangeable-candidates prior. This is the ranker's job — ordering the
    parameterisations of one strategy family against *each other* — so it is the
    default. The precision weighting means a wildly-noisy candidate barely moves
    the target, so a lucky spike cannot drag the field toward itself.

    ``ZERO`` — the no-edge null (shrink toward 0). Correct when the metric has a
    meaningful zero (no edge / no convexity) and the score feeds an accept/reject
    gate against the null rather than ordering peers — the finance multiple-testing
    convention (Jensen-Kelly-Pedersen; Chen-Zimmermann shrink alphas toward zero).
    Not the ranker's default; select it explicitly at the seam that gates
    admission. The target is a deliberate choice, never keyed off measured skew
    (an implicit, fragile knob at these grid sizes).
    """

    GRAND_MEAN = "grand_mean"
    ZERO = "zero"


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
    shrink_target: ShrinkTarget = ShrinkTarget.GRAND_MEAN,
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
    (Efron-Morris / James-Stein random effects), higher is better. Each
    candidate's raw score is the mean of its ranking metric across splits; that
    raw score is then shrunk toward ``shrink_target`` by a factor set by the
    candidate's *across-split* reliability (see :func:`_empirical_bayes_scores`).
    A candidate whose metric swings wildly across splits — e.g. one lucky spike
    carrying the mean — has a large standard error and is pulled hard toward the
    field, self-deflating the winner's curse; a steady, consistently high (convex)
    candidate keeps its raw score. When every candidate is perfectly consistent
    (zero across-split spread) the shrinkage vanishes and ranking reduces to the
    raw per-split mean. ``shrink_target`` defaults to the field's precision-weighted
    mean (:class:`ShrinkTarget.GRAND_MEAN`), the exchangeable-candidates prior
    proper to ranking peers; :class:`ShrinkTarget.ZERO` is for a no-edge admission
    gate, not peer ranking.

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
        [c.raw for c in raw_candidates],
        [c.se for c in raw_candidates],
        target=shrink_target,
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


def _empirical_bayes_scores(
    raws: list[float],
    ses: list[float | None],
    *,
    target: ShrinkTarget = ShrinkTarget.GRAND_MEAN,
) -> list[float]:
    """Empirical-Bayes posterior means shrinking each raw score toward a common target.

    ::

        shrunk = center + [tau2 / (tau2 + se**2)] * (raw - center)

    The pull is set by each candidate's across-split reliability: a large ``se``
    (a metric driven by one lucky split) shrinks hard toward the field, undoing
    the winner's curse without penalising a consistently high candidate. ``tau2``
    is the Paule-Mandel between-candidate variance (:func:`_paule_mandel_tau2`),
    less biased than the DerSimonian-Laird moment rule at these grid sizes.
    ``center`` is chosen by ``target`` (:class:`ShrinkTarget`): the random-effects
    precision-weighted field mean (``GRAND_MEAN``) or the no-edge null ``0``
    (``ZERO``). Under ``GRAND_MEAN`` the precision weighting down-weights a noisy
    candidate so it cannot drag the target toward its own lucky spike.
    """
    n = len(raws)
    known = [s for s in ses if s is not None]
    # A single-finite-split candidate has no measurable spread; treat it as
    # maximally unreliable (the largest observed se) so it shrinks hardest.
    fallback = max(known) if known else 0.0
    se2 = [(fallback if s is None else s) ** 2 for s in ses]
    tau2 = _paule_mandel_tau2(raws, se2)
    # Degenerate field: no between-candidate spread AND a noiseless candidate
    # (identical raws) — nothing to shrink, and the weighted mean is undefined.
    if tau2 == 0.0 and any(v == 0.0 for v in se2):
        return list(raws)
    if target is ShrinkTarget.ZERO:
        centers = [0.0] * n
    else:
        weights = [1.0 / (v + tau2) for v in se2]
        pooled = sum(w * r for w, r in zip(weights, raws, strict=True)) / sum(weights)
        centers = [pooled] * n
    return [
        center + (tau2 / (tau2 + v)) * (raw - center)
        for raw, v, center in zip(raws, se2, centers, strict=True)
    ]


# Paule-Mandel root-find controls: each bisection step halves the bracket, so 60
# steps resolve tau2 to ~1e-18 of its scale; the tiny probe tests homogeneity when
# a zero-se candidate makes Q(0) infinite. Neither is a tuning knob.
_PM_BISECTION_STEPS = 60
_PM_HOMOGENEITY_PROBE = 1e-12


def _paule_mandel_tau2(raws: list[float], se2: list[float]) -> float:
    """Paule-Mandel estimate of the between-candidate variance ``tau2``.

    ``tau2`` is the value that makes the generalised Cochran statistic equal its
    degrees of freedom, ``Q(tau2) = k - 1`` (Paule & Mandel 1982), where
    ``Q(t) = sum_i (raw_i - mu_w)^2 / (se_i^2 + t)`` with ``mu_w`` the
    precision-weighted mean at ``t``. ``Q`` is strictly decreasing in ``t`` so the
    root is unique; it is found by bisection. Preferred over the DerSimonian-Laird
    moment estimator, which is documented to be biased at small ``k`` (Veroniki
    et al. 2016; Langan et al. 2019). Returns ``0`` when the across-split noise
    already explains the spread (no heterogeneity).
    """
    k = len(raws)
    if k < 2:
        return 0.0
    target = float(k - 1)

    def q(tau2: float) -> float:
        weights = [1.0 / (v + tau2) for v in se2]
        mu = sum(w * r for w, r in zip(weights, raws, strict=True)) / sum(weights)
        return sum(w * (r - mu) ** 2 for w, r in zip(weights, raws, strict=True))

    # Q(0+) is finite when every se is positive and +inf when any se is zero. If
    # even a hair above zero it is already <= k-1, the spread is within noise.
    probe = 0.0 if all(v > 0.0 for v in se2) else _PM_HOMOGENEITY_PROBE * (pvariance(raws) + 1.0)
    if q(probe) <= target:
        return 0.0
    lo, hi = 0.0, pvariance(raws) + max(se2) + 1.0
    while q(hi) > target:
        hi *= 2.0
    for _ in range(_PM_BISECTION_STEPS):
        mid = 0.5 * (lo + hi)
        if q(mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None
