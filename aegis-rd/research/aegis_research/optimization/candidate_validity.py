"""Candidate validity: verdict-based exclusion rules.

Owns every exclusion rule in one module behind a verdict value object.

- Invalid rule (pre-score): indicator output entirely non-finite over the full
  series (lookback exceeds all available history).
- Non-trading rule (post-score): no finite ranking score across splits.
- Under-traded rule (post-score): fewer than min_trades closed trades on the
  thinnest scored split.

Verdicts is a precedence-ordered four-way partition:
invalid > non_trading > under_traded > valid.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from research.aegis_research.optimization.candidate_grid import (
    CandidateGrid,
    SplitMetrics,
)
from research.aegis_research.optimization.precompute import (
    CandidateKey,
    IndicatorPrecompute,
)

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


def invalid_candidates(
    store: IndicatorPrecompute, keys: Sequence[CandidateKey]
) -> set[CandidateKey]:
    """Return keys of Candidates whose Indicator output is entirely non-finite.

    A Candidate is Invalid when at least one Indicator output block is entirely
    non-finite (all-NaN / all-inf) over the full series. This covers
    misconfigurations where an indicator's lookback exceeds the entire available
    history. A non-numeric output block is a broken Indicator contract and
    raises TypeError rather than being classified.
    """
    outputs = store.outputs
    if not outputs or store.n_symbols < 1:
        return set()

    invalid: set[CandidateKey] = set()
    for key in keys:
        for output_name, output in outputs.items():
            position = store._candidate_index_for_output(output_name)[key]
            if _candidate_output_is_non_finite(output, position, store.n_symbols):
                invalid.add(key)
                break
    return invalid


def invalid_candidate_positions(
    keys: Sequence[CandidateKey], invalid_keys: set[CandidateKey]
) -> list[int]:
    """Return the positional indices within ``keys`` that are Invalid."""
    return [position for position, key in enumerate(keys) if key in invalid_keys]


def _candidate_output_is_non_finite(output: Any, position: int, n_symbols: int) -> bool:
    start = position * n_symbols
    stop = start + n_symbols
    block = np.asarray(output)[:, start:stop]
    return block.size == 0 or not _has_finite_value(block)


def _has_finite_value(values: Any) -> bool:
    # A non-numeric block is a broken Indicator contract: np.isfinite raises
    # TypeError and the failure propagates instead of being classified.
    return bool(np.isfinite(values).any())
