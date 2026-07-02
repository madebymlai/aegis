"""Candidate validity: verdict-based exclusion rules.

Classifies every Candidate into one precedence-ordered verdict partition behind a
verdict value object.

- Invalid rule (pre-score): supplied as ``invalid_keys``. Detection lives on the
  precompute store (``IndicatorPrecompute.invalid_keys``), which owns the
  full-series non-finite scan because the outputs are its own data; this module
  classifies the verdict from the set the store detected.
- Non-trading rule (post-score): no finite ranking score across splits.
- Under-traded rule (post-score): fewer than min_trades closed trades on the
  thinnest scored split.

Verdicts is a precedence-ordered four-way partition:
invalid > non_trading > under_traded > valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research.aegis_research.optimization.candidate_grid import (
    CandidateGrid,
    SplitMetrics,
)
from research.aegis_research.optimization.precompute import CandidateKey

TRADES_METRIC = "total_trades"


@dataclass(frozen=True)
class Verdicts:
    """Precedence-ordered four-way partition of Candidates.

    Every Candidate is classified into exactly one bucket by precedence:
    invalid > non_trading > under_traded > valid.

    Counts are derived from the partition by construction — the invariant
    ``excluded_invalid <= excluded_degenerate <= total`` cannot be violated.
    """

    invalid: set[CandidateKey] = field(default_factory=set)
    non_trading: set[CandidateKey] = field(default_factory=set)
    under_traded: set[CandidateKey] = field(default_factory=set)
    valid: set[CandidateKey] = field(default_factory=set)

    @property
    def excluded_invalid(self) -> int:
        return len(self.invalid)

    @property
    def excluded_degenerate(self) -> int:
        return len(self.invalid) + len(self.non_trading) + len(self.under_traded)

    @property
    def total(self) -> int:
        return (
            len(self.invalid)
            + len(self.non_trading)
            + len(self.under_traded)
            + len(self.valid)
        )

    @property
    def admissible(self) -> set[CandidateKey]:
        """The set of valid (admissible) Candidate keys."""
        return self.valid


def classify_candidates(
    grid: CandidateGrid,
    *,
    invalid_keys: set[CandidateKey],
    min_trades: int,
    metric: str,
) -> Verdicts:
    """Classify every Candidate in ``grid`` into a four-way verdict partition.

    Precedence order: invalid > non_trading > under_traded > valid.

    * **invalid** — the Candidate key appears in ``invalid_keys`` (pre-score
      Invalid rule: indicator output entirely non-finite over full history).
    * **non_trading** — the Candidate has no finite ranking score across any
      split (the ``metric`` is None on every split in ``grid``).
    * **under_traded** — when ``min_trades > 0``, the Candidate's closed-trade
      count (``total_trades`` metric) falls below ``min_trades`` on the
      thinnest split it scored.
    * **valid** — none of the above.

    Returns a ``Verdicts`` whose counts satisfy
    ``excluded_invalid <= excluded_degenerate <= total`` by construction.
    Raises ``KeyError`` when ``metric`` is not a grid column.
    """
    metric_ids = grid.metric_ids
    if metric not in metric_ids:
        raise KeyError(f"ranking metric {metric!r} not present in grid columns")

    invalid: set[CandidateKey] = set()
    non_trading: set[CandidateKey] = set()
    under_traded: set[CandidateKey] = set()
    valid: set[CandidateKey] = set()

    for key_tuple, split_metrics in grid.by_candidate():
        if key_tuple in invalid_keys:
            invalid.add(key_tuple)
        else:
            if all(m[metric] is None for m in split_metrics.values()):
                non_trading.add(key_tuple)
            elif not _meets_trade_floor(split_metrics, min_trades, metric_ids):
                under_traded.add(key_tuple)
            else:
                valid.add(key_tuple)

    return Verdicts(
        invalid=invalid,
        non_trading=non_trading,
        under_traded=under_traded,
        valid=valid,
    )


def _meets_trade_floor(
    split_metrics: SplitMetrics,
    min_trades: int,
    metric_ids: list[str],
) -> bool:
    """Whether a candidate clears the per-split trade floor.

    The floor is disabled when ``min_trades <= 0``. Otherwise the candidate must
    have closed at least ``min_trades`` trades on the *thinnest* split it
    actually scored: splits where the candidate did not trade (None in
    ``total_trades``) are skipped. The trade-count column's absence is checked
    via ``metric_ids``.
    """
    if min_trades <= 0:
        return True
    if TRADES_METRIC not in metric_ids:
        return False
    counts = [
        v
        for metrics in split_metrics.values()
        if (v := metrics.get(TRADES_METRIC)) is not None
    ]
    return len(counts) > 0 and min(counts) >= min_trades
