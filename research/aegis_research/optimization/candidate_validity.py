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
import pandas as pd

from research.aegis_research.optimization.precompute import (
    CandidateKey,
    WideIndicatorPrecompute,
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
    grid: pd.DataFrame,
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
      split (``grid[metric].isna().all()`` per candidate group).
    * **under_traded** — when ``min_trades > 0``, the Candidate's closed-trade
      count (``total_trades`` column) falls below ``min_trades`` on the
      thinnest split it scored.
    * **valid** — none of the above.

    Returns a ``Verdicts`` whose counts satisfy
    ``excluded_invalid <= excluded_degenerate <= total`` by construction.
    """
    split_level = "split"
    if split_level not in grid.index.names:
        raise ValueError(f"grid index must include a {split_level!r} level")
    param_levels = [name for name in grid.index.names if name != split_level]
    if not param_levels:
        raise ValueError("grid index must carry at least one parameter level")
    group_level = param_levels[0] if len(param_levels) == 1 else param_levels

    invalid: set[CandidateKey] = set()
    non_trading: set[CandidateKey] = set()
    under_traded: set[CandidateKey] = set()
    valid: set[CandidateKey] = set()

    for key, sub in grid.groupby(level=group_level, sort=True):
        key_tuple: CandidateKey = key if isinstance(key, tuple) else (key,)

        if key_tuple in invalid_keys:
            invalid.add(key_tuple)
        elif sub[metric].isna().all():
            non_trading.add(key_tuple)
        elif not _meets_trade_floor(sub, min_trades):
            under_traded.add(key_tuple)
        else:
            valid.add(key_tuple)

    return Verdicts(
        invalid=invalid,
        non_trading=non_trading,
        under_traded=under_traded,
        valid=valid,
    )


def _meets_trade_floor(sub: pd.DataFrame, min_trades: int) -> bool:
    """Whether a candidate's grid subset clears the per-split trade floor.

    The floor is disabled when ``min_trades <= 0``. Otherwise the candidate must
    have closed at least ``min_trades`` trades on the *thinnest* split it
    actually scored: splits where the candidate did not trade (NaN in
    ``total_trades``) are skipped.
    """
    if min_trades <= 0:
        return True
    if TRADES_METRIC not in sub.columns:
        return False
    counts = sub[TRADES_METRIC].dropna()
    return len(counts) > 0 and counts.min() >= min_trades


def invalid_candidates(
    store: WideIndicatorPrecompute, keys: Sequence[CandidateKey]
) -> set[CandidateKey]:
    """Return keys of Candidates whose Indicator output is entirely non-finite.

    A Candidate is Invalid when at least one Indicator output block is entirely
    non-finite (all-NaN / all-inf) over the full series. This covers
    misconfigurations where an indicator's lookback exceeds the entire available
    history.
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
    try:
        return bool(np.isfinite(values).any())
    except TypeError:
        return bool(pd.notna(values).any())
