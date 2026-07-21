"""Verdict-based exclusion rules over complete continuous Candidate paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

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


def classify_continuous_candidates(
    metrics: pd.DataFrame,
    *,
    invalid_keys: set[CandidateKey],
    min_trades: int,
    metric: str,
) -> Verdicts:
    """Classify Candidates from their complete continuous-path Metrics."""
    if metric not in metrics.columns:
        raise KeyError(f"ranking metric {metric!r} not present in metric columns")

    invalid: set[CandidateKey] = set()
    non_trading: set[CandidateKey] = set()
    under_traded: set[CandidateKey] = set()
    valid: set[CandidateKey] = set()
    for raw_key, row in metrics.iterrows():
        key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        if key in invalid_keys:
            invalid.add(key)
            continue
        score = row[metric]
        trades = row.get(TRADES_METRIC)
        if not _finite(score) or (TRADES_METRIC in metrics.columns and not _positive(trades)):
            non_trading.add(key)
        elif min_trades > 0 and (not _finite(trades) or float(trades) < min_trades):
            under_traded.add(key)
        else:
            valid.add(key)
    return Verdicts(
        invalid=invalid,
        non_trading=non_trading,
        under_traded=under_traded,
        valid=valid,
    )


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(value))
    except TypeError:
        return False


def _positive(value: Any) -> bool:
    return _finite(value) and float(value) > 0
