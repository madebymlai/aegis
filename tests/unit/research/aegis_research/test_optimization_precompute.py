"""Unit tests for the WideIndicatorPrecompute store.

The store holds indicator outputs computed once over the full series, addressed
candidate-major (each candidate owns a contiguous ``n_symbols`` column block) and
sliceable by split range. Its single behaviour is to return, for a window range
and an ordered set of candidate keys, the matching rows by candidate-major columns.
"""

from __future__ import annotations

import numpy as np

from research.aegis_research.optimization.precompute import (
    WideIndicatorPrecompute,
    build_candidate_index,
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
    store = WideIndicatorPrecompute(
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
    store = WideIndicatorPrecompute(
        outputs={"sig": arr},
        candidate_index={("A", 1): 0, ("A", 2): 1, ("B", 1): 2, ("B", 2): 3},
        n_symbols=n_symbols,
        output_candidate_index={
            "sig": {("A", 1): 0, ("A", 2): 0, ("B", 1): 1, ("B", 2): 1}
        },
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
