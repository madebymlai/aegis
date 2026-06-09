"""Unit tests for candidate_validity.invalid_candidates (Invalid rule).

Builds WideIndicatorPrecompute stores by hand and asserts the Invalid Candidate
keys — those whose Indicator output block is entirely non-finite over the full
series — are detected without a full Run. Prior art: test_optimization_precompute.py.
"""

from __future__ import annotations

import numpy as np

from research.aegis_research.optimization.candidate_validity import invalid_candidates
from research.aegis_research.optimization.precompute import (
    WideIndicatorPrecompute,
    build_candidate_index,
    candidate_keys,
)


def _store(
    outputs: dict[str, np.ndarray],
    n_symbols: int,
    param_lists: dict[str, list],
) -> WideIndicatorPrecompute:
    return WideIndicatorPrecompute(
        outputs=outputs,
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def test_empty_store_returns_empty_set() -> None:
    store = _store(outputs={}, n_symbols=2, param_lists={"window": [5, 10]})
    keys = candidate_keys({"window": [5, 10]})
    assert invalid_candidates(store, keys) == set()


def test_zero_symbols_returns_empty_set() -> None:
    store = _store(
        outputs={"sig": np.array([[1.0, 2.0]])},
        n_symbols=0,
        param_lists={"window": [5]},
    )
    keys = candidate_keys({"window": [5]})
    assert invalid_candidates(store, keys) == set()


def test_no_keys_returns_empty_set() -> None:
    store = _store(
        outputs={"sig": np.array([[1.0, 2.0]])},
        n_symbols=2,
        param_lists={"window": []},
    )
    assert invalid_candidates(store, []) == set()


def test_all_finite_blocks_returns_empty_set() -> None:
    # 2 rows, 2 candidates x 2 symbols = 4 cols.  Candidate A cols 0:2, B cols 2:4.
    outputs = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [5.0, 6.0, 7.0, 8.0],
    ])
    store = _store(
        outputs={"mom": outputs},
        n_symbols=2,
        param_lists={"window": [5, 10]},
    )
    keys = candidate_keys({"window": [5, 10]})
    assert invalid_candidates(store, keys) == set()


def test_one_all_non_finite_block_returns_that_key() -> None:
    """Candidate B (cols 2:4) is all-NaN; A (cols 0:2) is finite."""
    outputs = np.array([
        [1.0, 2.0, np.nan, np.nan],
        [3.0, 4.0, np.nan, np.nan],
    ])
    store = _store(
        outputs={"mom": outputs},
        n_symbols=2,
        param_lists={"window": [5, 10]},
    )
    keys = candidate_keys({"window": [5, 10]})
    # Sorted param names -> keys are (window=5) and (window=10)
    # candidate_index is built from sorted param_lists:
    #   window=5 -> position 0 (cols 0:2), window=10 -> position 1 (cols 2:4)
    assert invalid_candidates(store, keys) == {(10,)}


def test_any_output_non_finite_makes_candidate_invalid() -> None:
    """Two outputs; Candidate A is finite in 'mom' but all-NaN in 'vol'."""
    n_symbols = 1
    # Candidate A (position 0, col 0): finite in mom, NaN in vol
    # Candidate B (position 1, col 1): finite in both
    mom = np.array([
        [1.0, 2.0],
        [3.0, 4.0],
        [5.0, 6.0],
    ])
    vol = np.array([
        [np.nan, 1.0],
        [np.nan, 2.0],
        [np.nan, 3.0],
    ])
    store = _store(
        outputs={"mom": mom, "vol": vol},
        n_symbols=n_symbols,
        param_lists={"alpha": [0.5, 1.0]},
    )
    keys = candidate_keys({"alpha": [0.5, 1.0]})
    # alpha=0.5 -> position 0, alpha=1.0 -> position 1
    # A (alpha=0.5) has NaN in 'vol' -> invalid
    assert invalid_candidates(store, keys) == {(0.5,)}


def test_all_inf_block_is_non_finite() -> None:
    """An all-inf block should be treated the same as all-NaN."""
    outputs = np.array([
        [1.0, np.inf],
        [2.0, np.inf],
    ])
    store = _store(
        outputs={"sig": outputs},
        n_symbols=1,
        param_lists={"p": [1, 2]},
    )
    keys = candidate_keys({"p": [1, 2]})
    assert invalid_candidates(store, keys) == {(2,)}


def test_multiple_candidates_all_invalid() -> None:
    outputs = np.full((3, 4), np.nan)  # 3 rows, 2 candidates x 2 symbols
    store = _store(
        outputs={"sig": outputs},
        n_symbols=2,
        param_lists={"lag": [1, 2]},
    )
    keys = candidate_keys({"lag": [1, 2]})
    assert invalid_candidates(store, keys) == {(1,), (2,)}


def test_respects_output_candidate_index_dedup() -> None:
    """When output_candidate_index maps multiple full keys to the same block,
    the non-finite check still operates correctly on the deduped column block."""
    n_symbols = 1
    outputs = np.array([
        [np.nan, 1.0],   # position 0 all-NaN, position 1 finite
        [np.nan, 2.0],
    ])
    full_index = build_candidate_index({"x": [1, 2, 3], "y": [10, 10, 10]})
    # sorted names: x, y
    # (1, 10): 0, (2, 10): 1, (3, 10): 2 — but y is always 10 so duplicate for indicator
    output_index = {
        "sig": {(1, 10): 0, (2, 10): 0, (3, 10): 1}  # (1,10) and (2,10) share block 0
    }
    store = WideIndicatorPrecompute(
        outputs={"sig": outputs},
        candidate_index=full_index,
        n_symbols=n_symbols,
        output_candidate_index=output_index,
    )
    keys = candidate_keys({"x": [1, 2, 3], "y": [10, 10, 10]})
    # Block 0 (shared by (1,10) and (2,10)) is all-NaN, block 1 is finite
    assert invalid_candidates(store, keys) == {(1, 10), (2, 10)}
