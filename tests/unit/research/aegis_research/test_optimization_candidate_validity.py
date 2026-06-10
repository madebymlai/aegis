"""Unit tests for candidate_validity (Invalid rule + classify_candidates).

Invalid rule tests build WideIndicatorPrecompute stores by hand and assert the
Invalid Candidate keys are detected without a full Run.

Classify-candidates tests exercise the four-way precedence-ordered verdict
partition (invalid > non_trading > under_traded > valid) using
``make_candidate_grid`` — the one factory that speaks the boundary vocabulary.
Prior art: test_optimization_precompute.py, test_optimization_ranking.py.
"""

from __future__ import annotations

import numpy as np

from research.aegis_research.optimization.candidate_validity import (
    Verdicts,
    classify_candidates,
    invalid_candidates,
)
from research.aegis_research.optimization.precompute import (
    WideIndicatorPrecompute,
    build_candidate_index,
    candidate_keys,
)
from tests.support.research.aegis_research.factories import make_candidate_grid


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


# ---------------------------------------------------------------------------
# classify_candidates — basic classification
# ---------------------------------------------------------------------------


def test_classify_valid_candidate() -> None:
    grid = make_candidate_grid({("A",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 0.5}}})
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    assert verdict.valid == {("A",)}
    assert verdict.invalid == set()
    assert verdict.non_trading == set()
    assert verdict.under_traded == set()
    assert verdict.total == 1
    assert verdict.excluded_invalid == 0
    assert verdict.excluded_degenerate == 0


def test_classify_invalid_candidate_with_finite_score_reported_invalid_not_non_trading() -> None:
    """An Invalid Candidate with a finite 0.0 row must be reported invalid,
    not non_trading. The Invalid stamp wins by precedence regardless of the
    finite score the cash-holding strategy would simulate to."""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("bad_lookback",): {"s0": {"sharpe": 0.0}, "s1": {"sharpe": 0.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys={("bad_lookback",)}, min_trades=0, metric="sharpe"
    )

    assert verdict.valid == {("good",)}
    assert verdict.invalid == {("bad_lookback",)}
    assert verdict.non_trading == set()
    assert verdict.under_traded == set()
    assert verdict.total == 2
    assert verdict.excluded_invalid == 1
    assert verdict.excluded_degenerate == 1


def test_classify_non_trading_candidate_all_nan_metric() -> None:
    """A Candidate whose ranking metric is all-NaN across every split is non_trading."""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("ghost",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    assert verdict.valid == {("good",)}
    assert verdict.non_trading == {("ghost",)}
    assert verdict.invalid == set()
    assert verdict.under_traded == set()
    assert verdict.total == 2
    assert verdict.excluded_degenerate == 1


def test_classify_under_traded_candidate() -> None:
    """A Candidate below the min_trades floor is under_traded."""
    grid = make_candidate_grid({
        ("fat",): {"s0": {"sharpe": 0.6, "total_trades": 40.0}, "s1": {"sharpe": 0.6, "total_trades": 38.0}},
        ("thin",): {"s0": {"sharpe": 2.0, "total_trades": 2.0}, "s1": {"sharpe": 2.0, "total_trades": 3.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys=set(), min_trades=10, metric="sharpe"
    )

    assert verdict.valid == {("fat",)}
    assert verdict.under_traded == {("thin",)}
    assert verdict.invalid == set()
    assert verdict.non_trading == set()
    assert verdict.total == 2
    assert verdict.excluded_degenerate == 1


def test_classify_under_traded_per_split_minimum() -> None:
    """A candidate must clear min_trades on the *thinnest* split it scored."""
    grid = make_candidate_grid({
        ("uneven",): {"s0": {"sharpe": 3.0, "total_trades": 50.0}, "s1": {"sharpe": 3.0, "total_trades": 4.0}},
        ("steady",): {"s0": {"sharpe": 0.5, "total_trades": 25.0}, "s1": {"sharpe": 0.5, "total_trades": 30.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys=set(), min_trades=10, metric="sharpe"
    )

    assert verdict.valid == {("steady",)}
    assert verdict.under_traded == {("uneven",)}
    assert verdict.excluded_degenerate == 1


def test_classify_min_trades_zero_disabled_all_valid() -> None:
    """When min_trades=0 the trade floor is disabled; all scored candidates are valid."""
    grid = make_candidate_grid({
        ("thin",): {"s0": {"sharpe": 2.0}, "s1": {"sharpe": 2.0}},
        ("fat",): {"s0": {"sharpe": 0.5}, "s1": {"sharpe": 0.5}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    assert verdict.valid == {("thin",), ("fat",)}
    assert verdict.under_traded == set()
    assert verdict.excluded_degenerate == 0


def test_classify_all_under_traded() -> None:
    """When every candidate is under_traded the verdict has no valid keys."""
    grid = make_candidate_grid({
        ("a",): {"s0": {"sharpe": 2.0, "total_trades": 2.0}, "s1": {"sharpe": 2.0, "total_trades": 3.0}},
        ("b",): {"s0": {"sharpe": 1.5, "total_trades": 1.0}, "s1": {"sharpe": 1.5, "total_trades": 4.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys=set(), min_trades=10, metric="sharpe"
    )

    assert verdict.valid == set()
    assert verdict.under_traded == {("a",), ("b",)}
    assert verdict.total == 2
    assert verdict.excluded_degenerate == 2


def test_classify_combined_exclusion_non_trading_and_under_traded() -> None:
    """Non-trading and under-traded exclusions combine in excluded_degenerate."""
    grid = make_candidate_grid({
        ("real",): {"s0": {"sharpe": 0.6, "total_trades": 40.0}, "s1": {"sharpe": 0.6, "total_trades": 40.0}},
        ("thin",): {"s0": {"sharpe": 2.0, "total_trades": 2.0}, "s1": {"sharpe": 2.0, "total_trades": 2.0}},
        ("dead",): {"s0": {"sharpe": None, "total_trades": 0.0}, "s1": {"sharpe": None, "total_trades": 0.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys=set(), min_trades=10, metric="sharpe"
    )

    assert verdict.valid == {("real",)}
    assert verdict.non_trading == {("dead",)}
    assert verdict.under_traded == {("thin",)}
    assert verdict.excluded_degenerate == 2
    assert verdict.total == 3


# ---------------------------------------------------------------------------
# classify_candidates — precedence
# ---------------------------------------------------------------------------


def test_classify_precedence_invalid_over_non_trading() -> None:
    """An Invalid Candidate that is also all-NaN is classified invalid, not non_trading."""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("bad",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(
        grid, invalid_keys={("bad",)}, min_trades=0, metric="sharpe"
    )

    assert verdict.valid == {("good",)}
    assert verdict.invalid == {("bad",)}
    assert verdict.non_trading == set()
    assert verdict.excluded_degenerate == 1
    assert verdict.excluded_invalid == 1


def test_classify_precedence_non_trading_over_under_traded() -> None:
    """A Candidate that is both all-NaN and under-traded is classified non_trading.
    (Constructed by giving an all-NaN candidate insufficient trades.)"""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 1.0, "total_trades": 40.0}, "s1": {"sharpe": 1.0, "total_trades": 40.0}},
        ("ghost",): {"s0": {"sharpe": None, "total_trades": 2.0}, "s1": {"sharpe": None, "total_trades": 3.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys=set(), min_trades=10, metric="sharpe"
    )

    # ghost is all-NaN AND under-traded -> non_trading wins by precedence
    assert verdict.valid == {("good",)}
    assert verdict.non_trading == {("ghost",)}
    assert verdict.under_traded == set()
    assert verdict.excluded_degenerate == 1


def test_classify_precedence_invalid_over_under_traded() -> None:
    """An Invalid Candidate that is also under-traded is classified invalid."""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 1.0, "total_trades": 40.0}, "s1": {"sharpe": 1.0, "total_trades": 40.0}},
        ("bad",): {"s0": {"sharpe": 2.0, "total_trades": 2.0}, "s1": {"sharpe": 2.0, "total_trades": 3.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys={("bad",)}, min_trades=10, metric="sharpe"
    )

    # bad has a finite score but is invalid AND under-traded -> invalid wins
    assert verdict.valid == {("good",)}
    assert verdict.invalid == {("bad",)}
    assert verdict.under_traded == set()
    assert verdict.excluded_degenerate == 1
    assert verdict.excluded_invalid == 1


def test_classify_precedence_invalid_beats_all() -> None:
    """A Candidate stamped invalid by pre-score is invalid regardless of
    any post-score properties (finite score, enough trades, etc.)."""
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 0.5, "total_trades": 40.0}, "s1": {"sharpe": 0.5, "total_trades": 40.0}},
        ("bad",): {"s0": {"sharpe": 2.0, "total_trades": 50.0}, "s1": {"sharpe": 2.0, "total_trades": 50.0}},
    })
    verdict = classify_candidates(
        grid, invalid_keys={("bad",)}, min_trades=10, metric="sharpe"
    )

    # bad would be the best by score AND clear the trade floor, but invalid wins
    assert verdict.valid == {("good",)}
    assert verdict.invalid == {("bad",)}
    assert verdict.excluded_degenerate == 1
    assert verdict.excluded_invalid == 1


# ---------------------------------------------------------------------------
# classify_candidates — Verdicts value object invariants
# ---------------------------------------------------------------------------


def test_verdicts_counts_satisfy_invariant() -> None:
    """excluded_invalid <= excluded_degenerate <= total for any Verdicts."""
    verdict = Verdicts(
        invalid={("a",)},
        non_trading={("b",), ("c",)},
        under_traded={("d",)},
        valid={("e",), ("f",), ("g",)},
    )

    assert verdict.excluded_invalid == 1
    assert verdict.excluded_degenerate == 4  # 1 + 2 + 1
    assert verdict.total == 7
    assert verdict.excluded_invalid <= verdict.excluded_degenerate <= verdict.total


def test_verdicts_empty_partition() -> None:
    """An empty partition has all-zero counts."""
    verdict = Verdicts()

    assert verdict.total == 0
    assert verdict.excluded_invalid == 0
    assert verdict.excluded_degenerate == 0
    assert verdict.admissible == set()


def test_classify_empty_grid() -> None:
    """An empty grid (no candidates) produces an empty Verdicts."""
    grid = make_candidate_grid({})
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    assert verdict.total == 0
    assert verdict.valid == set()
    assert verdict.excluded_degenerate == 0


def test_classify_all_valid_verdict_counts() -> None:
    """When all candidates are valid, counts reflect that."""
    grid = make_candidate_grid({
        ("A",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("B",): {"s0": {"sharpe": 0.5}, "s1": {"sharpe": 0.5}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    assert verdict.total == 2
    assert verdict.excluded_invalid == 0
    assert verdict.excluded_degenerate == 0
    assert len(verdict.valid) == 2
