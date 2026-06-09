"""Candidate validity: verdict-based exclusion rules (Invalid rule).

The Invalid rule: a Candidate is Invalid when an Indicator output is entirely
non-finite over the full series (lookback exceeds all available history).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.optimization.precompute import (
    CandidateKey,
    WideIndicatorPrecompute,
)


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
