"""Global, blocked Friedman ranking of fixed-parameter candidates across splits.

Every candidate is scored on the SAME splits, so the splits are a paired BLOCKING
factor: the fold-to-fold regime swing is common-mode variance shared by all
candidates. This module ranks candidates WITHIN each split and averages those
ranks (a randomized block design / Friedman two-way analysis by ranks; Demšar
2006, "Statistical Comparisons of Classifiers over Multiple Data Sets"). Ranking
within a block cancels the shared per-split variance so only the between-candidate
signal drives selection, and a single lucky split cannot inflate a candidate (it
is just one rank-1). The mean rank across splits is the ranking ``score`` — lower
is better.

This replaces an earlier empirical-Bayes point-``tau2`` scorer whose UNPAIRED
model left the regime variance inside each candidate's standard error: the
between-candidate signal was swamped, Paule-Mandel ``tau2`` clamped to exactly 0,
every candidate collapsed to one identical pooled score, and a blind
parameter-order tie-break then selected the lexicographic corner rather than the
real winner (aegis-rd-2xl4).

Exclusion rules live in ``candidate_validity``; ranking consumes the verdict
without re-deriving any exclusion logic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import ceil
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

    ``score`` is the candidate's Friedman **mean rank** across splits (rank 1 is
    the best-in-split); **lower is better**. It is not a per-split mean of the
    metric — the aggregated metric mean lives in ``metrics``.
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


def select_representative_candidates(
    grid: CandidateGrid,
    verdicts: Verdicts,
    *,
    metric: str,
) -> OptimizationResult:
    """Rank admissible (valid) candidates by blocked mean rank; return best/median/worst.

    ``grid`` is a CandidateGrid whose ``by_candidate()`` iterator yields
    per-Candidate ``(CandidateKey, split → metric_id → float-or-None)`` mappings
    with NaN already normalized to None. Iteration order is parameter-sorted and
    deterministic — ranking tie-stability rests on this contract.

    ``verdicts`` is a pre-computed ``Verdicts`` partition from
    ``candidate_validity.classify_candidates``. Only ``verdicts.valid``
    candidates are scored; excluded candidates (invalid, non_trading,
    under_traded) can never occupy a representative role.

    **Blocked Friedman ranking.** Within each split the admissible candidates are
    ranked on the chosen metric (highest value gets rank 1; average ranks for
    ties; a candidate with a missing/None metric on that split is ranked worst on
    that split, keeping every split on one ``1..k`` scale). A candidate's
    ``score`` is the mean of its per-split ranks — **lower is better**. Because
    every candidate is ranked on the same splits, the shared per-split (regime)
    variation cancels, and no single lucky split can carry a candidate.

    best/median/worst are ranked among the ``N`` admissible survivors: ``best`` is
    rank 1, ``median`` is rank ``ceil(N/2)``, and ``worst`` is rank N — all real,
    valid candidates. Ordering is ascending by mean rank; exact ties are broken by
    the higher aggregated metric mean, then by parameter-sorted order — never the
    blind parameter-only order that let the old scorer pick a bad corner under a
    collapsed tie. Raises ``ValueError`` when no candidate survives.

    ``OptimizationResult`` is constructed exactly once with counts copied
    straight from the verdict: no post-hoc patch is needed.
    """
    metric_ids = grid.metric_ids
    if metric not in metric_ids:
        raise KeyError(f"ranking metric {metric!r} not present in grid columns")

    param_levels = grid.param_levels
    admissible = verdicts.admissible
    split_metrics_by_key: dict[Any, Mapping[Any, Mapping[str, float | None]]] = {
        key_tuple: split_metrics
        for key_tuple, split_metrics in grid.by_candidate()
        if key_tuple in admissible
    }

    if not split_metrics_by_key:
        raise ValueError(
            f"no admissible candidate survived; all {verdicts.total} candidates "
            f"were excluded by the validity verdict (invalid={verdicts.excluded_invalid}, "
            f"non_trading={len(verdicts.non_trading)}, under_traded={len(verdicts.under_traded)})"
        )

    keys = list(split_metrics_by_key)
    split_labels = _ordered_split_labels(split_metrics_by_key.values())
    # Blocked ranking: rank all candidates within each split, then average.
    rank_sums = dict.fromkeys(keys, 0.0)
    for label in split_labels:
        values = [_metric_value(split_metrics_by_key[key], label, metric) for key in keys]
        for key, rank in zip(keys, _average_ranks(values), strict=True):
            rank_sums[key] += rank
    n_splits = len(split_labels)

    scored: list[_ScoredCandidate] = []
    for key_tuple in keys:
        split_metrics = split_metrics_by_key[key_tuple]
        aggregated = {
            col: _mean([split_metrics[s][col] for s in split_metrics])
            for col in metric_ids
        }
        scored.append(
            _ScoredCandidate(
                candidate=EvaluatedCandidate(
                    params=dict(zip(param_levels, key_tuple, strict=True)),
                    score=rank_sums[key_tuple] / n_splits,
                    selection_metrics=split_metrics,
                    metrics=aggregated,
                ),
                raw=aggregated[metric],
                key=key_tuple,
            )
        )

    ranked = [item.candidate for item in sorted(scored, key=_rank_key)]
    n = len(ranked)
    return OptimizationResult(
        best=ranked[0],
        median=ranked[ceil(n / 2) - 1],
        worst=ranked[n - 1],
        excluded_degenerate=verdicts.excluded_degenerate,
        excluded_invalid=verdicts.excluded_invalid,
        total_candidates=verdicts.total,
    )


@dataclass(frozen=True)
class _ScoredCandidate:
    """A candidate carried through selection with its sort keys."""

    candidate: EvaluatedCandidate
    raw: float | None
    key: tuple[Any, ...]


def _rank_key(item: _ScoredCandidate) -> tuple[float, float, tuple[Any, ...]]:
    """Ascending sort: lowest mean rank first; ties -> higher metric mean, then param order.

    The metric-mean tie-break (magnitude) means a genuine mean-rank tie resolves to
    the stronger candidate rather than an arbitrary lexicographic winner, and the
    final parameter-sorted key keeps the order deterministic and stable.
    """
    raw = item.raw
    raw_key = float("-inf") if raw is None else -raw
    return (item.candidate.score, raw_key, item.key)


def _ordered_split_labels(
    per_candidate: Iterable[Mapping[Any, Mapping[str, float | None]]],
) -> list[Any]:
    """Deterministic union of split labels across candidates (sorted by string form)."""
    labels: set[Any] = set()
    for split_metrics in per_candidate:
        labels.update(split_metrics.keys())
    return sorted(labels, key=repr)


def _metric_value(
    split_metrics: Mapping[Any, Mapping[str, float | None]],
    label: Any,
    metric: str,
) -> float | None:
    """This candidate's metric on ``label`` (None when the split or value is absent)."""
    return split_metrics.get(label, {}).get(metric)


def _average_ranks(values: list[float | None]) -> list[float]:
    """Average ranks over one split; best (highest finite value) = 1, None ranks worst.

    A None value (no finite metric on this split) is ranked below every finite
    value and tied with the other Nones, so each split keeps a single ``1..k``
    scale and its ranks stay comparable across splits. Ties (equal finite values,
    or Nones) share the average of the ranks they span.
    """
    n = len(values)
    order = sorted(
        range(n),
        key=lambda i: (values[i] is None, -values[i] if values[i] is not None else 0.0),
    )
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and _same_rank(values[order[i]], values[order[j + 1]]):
            j += 1
        average = (i + 1 + j + 1) / 2.0
        for pos in range(i, j + 1):
            ranks[order[pos]] = average
        i = j + 1
    return ranks


def _same_rank(a: float | None, b: float | None) -> bool:
    """Two split values share a rank when both are None or both equal finite values."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None
