"""Unit tests for the IndicatorPrecompute store.

The store holds indicator outputs computed once over the full series, addressed
candidate-major (each candidate owns a contiguous ``n_symbols`` column block) and
sliceable by split range. The no-look-ahead validation helper encodes the causal
prefix-equivalence invariant required by full-series precompute reuse.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.optimization.precompute import (
    IndicatorPrecompute,
    PrecomputeCausalityError,
    build_candidate_index,
    validate_precompute_no_lookahead,
)


def _candidate_major_array(n_rows: int, n_candidates: int, n_symbols: int) -> np.ndarray:
    """Distinctive value per (row, candidate, symbol) so mis-addressing is visible."""
    arr = np.empty((n_rows, n_candidates * n_symbols))
    for row in range(n_rows):
        for candidate in range(n_candidates):
            for symbol in range(n_symbols):
                arr[row, candidate * n_symbols + symbol] = candidate * 100 + symbol * 10 + row
    return arr


def test_window_selects_rows_and_gathers_candidate_columns_in_requested_order() -> None:
    n_rows, n_candidates, n_symbols = 6, 3, 2
    arr = _candidate_major_array(n_rows, n_candidates, n_symbols)
    store = IndicatorPrecompute(
        outputs={"sig": arr},
        candidate_index={("A",): 0, ("B",): 1, ("C",): 2},
        n_symbols=n_symbols,
    )

    # Slice rows [2, 5) and gather candidate C then A (reordered subset).
    window = store.window(slice(2, 5), [("C",), ("A",)])

    assert set(window) == {"sig"}
    assert window["sig"].shape == (3, 2 * n_symbols)
    # First block is candidate C (index 2 -> columns 4:6), second is A (index 0 -> 0:2).
    np.testing.assert_array_equal(window["sig"][:, 0:2], arr[2:5, 4:6])
    np.testing.assert_array_equal(window["sig"][:, 2:4], arr[2:5, 0:2])


def test_window_can_use_output_specific_deduped_candidate_index() -> None:
    n_rows, n_symbols = 4, 1
    arr = _candidate_major_array(n_rows, n_candidates=2, n_symbols=n_symbols)
    store = IndicatorPrecompute(
        outputs={"sig": arr},
        candidate_index={("A", 1): 0, ("A", 2): 1, ("B", 1): 2, ("B", 2): 3},
        n_symbols=n_symbols,
        output_candidate_index={"sig": {("A", 1): 0, ("A", 2): 0, ("B", 1): 1, ("B", 2): 1}},
    )

    window = store.window(slice(1, 3), [("A", 2), ("B", 1), ("A", 1)])

    assert window["sig"].shape == (2, 3 * n_symbols)
    np.testing.assert_array_equal(window["sig"][:, 0:1], arr[1:3, 0:1])
    np.testing.assert_array_equal(window["sig"][:, 1:2], arr[1:3, 1:2])
    np.testing.assert_array_equal(window["sig"][:, 2:3], arr[1:3, 0:1])


def test_build_candidate_index_is_order_independent_in_param_name() -> None:
    # Two candidates over two params; index keys are canonical (sorted param name).
    param_lists = {"window": [5, 50], "smooth": [3, 7]}
    index = build_candidate_index(param_lists)

    # Canonical key order is sorted param names -> ("smooth", "window") value tuple.
    assert index == {(3, 5): 0, (7, 50): 1}


def _close_frame(n_rows: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {"AAA": np.arange(n_rows, dtype=float), "BBB": np.arange(n_rows, dtype=float) + 100.0}
    )


def _lagged_delta_precompute(
    close: pd.DataFrame, n_candidates: int, **param_lists
) -> IndicatorPrecompute:
    prices = close.to_numpy()
    n_rows, n_symbols = prices.shape
    outputs = np.full((n_rows, n_candidates * n_symbols), np.nan)
    for candidate, lag in enumerate(param_lists["lag"]):
        if lag < n_rows:
            outputs[lag:, candidate * n_symbols : (candidate + 1) * n_symbols] = (
                prices[lag:] - prices[:-lag]
            )
    return IndicatorPrecompute(
        outputs={"delta": outputs},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def _future_delta_precompute(
    close: pd.DataFrame, n_candidates: int, **param_lists
) -> IndicatorPrecompute:
    prices = close.to_numpy()
    n_rows, n_symbols = prices.shape
    outputs = np.full((n_rows, n_candidates * n_symbols), np.nan)
    for candidate, horizon in enumerate(param_lists["horizon"]):
        if horizon < n_rows:
            outputs[:-horizon, candidate * n_symbols : (candidate + 1) * n_symbols] = (
                prices[horizon:] - prices[:-horizon]
            )
    return IndicatorPrecompute(
        outputs={"delta": outputs},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def test_precompute_no_lookahead_contract_accepts_causal_prefix_equivalence() -> None:
    validate_precompute_no_lookahead(
        _lagged_delta_precompute,
        _close_frame(),
        ranges=[slice(3, 7), slice(6, 10)],
        n_candidates=2,
        lag=[1, 3],
    )


def test_precompute_no_lookahead_contract_rejects_future_dependent_outputs() -> None:
    with pytest.raises(PrecomputeCausalityError, match="future rows"):
        validate_precompute_no_lookahead(
            _future_delta_precompute,
            _close_frame(),
            ranges=[slice(3, 7)],
            n_candidates=1,
            horizon=[2],
        )


# ---------------------------------------------------------------------------
# IndicatorPrecompute.invalid_keys — full-series non-finite detection
#
# A candidate is Invalid when at least one indicator output block is entirely
# non-finite over the full series (its lookback exceeds all available history).
# The store detects this over its own candidate_index; these tests build stores
# by hand and assert the Invalid set without a full Run.
# ---------------------------------------------------------------------------


def _invalid_keys_store(
    outputs: dict[str, np.ndarray],
    n_symbols: int,
    param_lists: dict[str, list],
) -> IndicatorPrecompute:
    return IndicatorPrecompute(
        outputs=outputs,
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def test_invalid_keys_empty_store_returns_empty_set() -> None:
    store = _invalid_keys_store(outputs={}, n_symbols=2, param_lists={"window": [5, 10]})
    assert store.invalid_keys == set()


def test_invalid_keys_zero_symbols_returns_empty_set() -> None:
    store = _invalid_keys_store(
        outputs={"sig": np.array([[1.0, 2.0]])},
        n_symbols=0,
        param_lists={"window": [5]},
    )
    assert store.invalid_keys == set()


def test_invalid_keys_non_numeric_output_block_raises_type_error() -> None:
    """A non-numeric Indicator output block is a broken contract, not a verdict."""
    store = _invalid_keys_store(
        outputs={"sig": np.array([[None, 1.0]], dtype=object)},
        n_symbols=2,
        param_lists={"window": [5]},
    )

    with pytest.raises(TypeError):
        _ = store.invalid_keys


def test_invalid_keys_store_with_no_candidates_returns_empty_set() -> None:
    store = _invalid_keys_store(
        outputs={"sig": np.array([[1.0, 2.0]])},
        n_symbols=2,
        param_lists={"window": []},
    )
    assert store.invalid_keys == set()


def test_invalid_keys_all_finite_blocks_returns_empty_set() -> None:
    # 2 rows, 2 candidates x 2 symbols = 4 cols.  Candidate A cols 0:2, B cols 2:4.
    outputs = np.array(
        [
            [1.0, 2.0, 3.0, 4.0],
            [5.0, 6.0, 7.0, 8.0],
        ]
    )
    store = _invalid_keys_store(
        outputs={"mom": outputs},
        n_symbols=2,
        param_lists={"window": [5, 10]},
    )
    assert store.invalid_keys == set()


def test_invalid_keys_one_all_non_finite_block_returns_that_key() -> None:
    """Candidate B (cols 2:4) is all-NaN; A (cols 0:2) is finite."""
    outputs = np.array(
        [
            [1.0, 2.0, np.nan, np.nan],
            [3.0, 4.0, np.nan, np.nan],
        ]
    )
    store = _invalid_keys_store(
        outputs={"mom": outputs},
        n_symbols=2,
        param_lists={"window": [5, 10]},
    )
    # Sorted param names -> keys are (window=5) and (window=10):
    #   window=5 -> position 0 (cols 0:2), window=10 -> position 1 (cols 2:4)
    assert store.invalid_keys == {(10,)}


def test_invalid_keys_any_output_non_finite_makes_candidate_invalid() -> None:
    """Two outputs; Candidate A is finite in 'mom' but all-NaN in 'vol'."""
    # Candidate A (position 0, col 0): finite in mom, NaN in vol
    # Candidate B (position 1, col 1): finite in both
    mom = np.array(
        [
            [1.0, 2.0],
            [3.0, 4.0],
            [5.0, 6.0],
        ]
    )
    vol = np.array(
        [
            [np.nan, 1.0],
            [np.nan, 2.0],
            [np.nan, 3.0],
        ]
    )
    store = _invalid_keys_store(
        outputs={"mom": mom, "vol": vol},
        n_symbols=1,
        param_lists={"alpha": [0.5, 1.0]},
    )
    # alpha=0.5 -> position 0 has NaN in 'vol' -> invalid
    assert store.invalid_keys == {(0.5,)}


def test_invalid_keys_all_inf_block_is_non_finite() -> None:
    """An all-inf block should be treated the same as all-NaN."""
    outputs = np.array(
        [
            [1.0, np.inf],
            [2.0, np.inf],
        ]
    )
    store = _invalid_keys_store(
        outputs={"sig": outputs},
        n_symbols=1,
        param_lists={"p": [1, 2]},
    )
    assert store.invalid_keys == {(2,)}


def test_invalid_keys_multiple_candidates_all_invalid() -> None:
    outputs = np.full((3, 4), np.nan)  # 3 rows, 2 candidates x 2 symbols
    store = _invalid_keys_store(
        outputs={"sig": outputs},
        n_symbols=2,
        param_lists={"lag": [1, 2]},
    )
    assert store.invalid_keys == {(1,), (2,)}


def test_invalid_keys_respects_output_candidate_index_dedup() -> None:
    """When output_candidate_index maps multiple full keys to the same block,
    the non-finite check still operates correctly on the deduped column block."""
    outputs = np.array(
        [
            [np.nan, 1.0],  # position 0 all-NaN, position 1 finite
            [np.nan, 2.0],
        ]
    )
    full_index = build_candidate_index({"x": [1, 2, 3], "y": [10, 10, 10]})
    # sorted names x, y -> (1,10):0, (2,10):1, (3,10):2 in the full index; the
    # indicator deduped y (always 10) so (1,10) and (2,10) share block 0.
    output_index = {"sig": {(1, 10): 0, (2, 10): 0, (3, 10): 1}}
    store = IndicatorPrecompute(
        outputs={"sig": outputs},
        candidate_index=full_index,
        n_symbols=1,
        output_candidate_index=output_index,
    )
    # Block 0 (shared by (1,10) and (2,10)) is all-NaN, block 1 is finite
    assert store.invalid_keys == {(1, 10), (2, 10)}

