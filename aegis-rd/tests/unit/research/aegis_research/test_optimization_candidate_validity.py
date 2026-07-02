"""Unit tests for candidate_validity's classify_candidates.

Exercises the four-way precedence-ordered verdict partition
(invalid > non_trading > under_traded > valid) using ``make_candidate_grid`` —
the one factory that speaks the boundary vocabulary. Invalid-Candidate *detection*
itself lives on the precompute store (``IndicatorPrecompute.invalid_keys``); its
tests live in test_optimization_precompute.py. classify_candidates receives the
detected set as ``invalid_keys`` and classifies the verdict.
Prior art: test_optimization_precompute.py, test_optimization_ranking.py.
"""

from __future__ import annotations

import pytest

from research.aegis_research.optimization.candidate_validity import (
    Verdicts,
    classify_candidates,
)
from research.aegis_research.optimization.precompute import candidate_keys
from tests.support.research.aegis_research.factories import make_candidate_grid

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


def test_classify_matches_invalid_key_when_grid_param_order_differs_from_sorted() -> None:
    """Regression (aegis-rd-948): the store's ``invalid_keys`` returns canonical
    sorted-name keys (buffer_band before entry_band), while a grid is emitted in the
    sweep's param order (entry_band before buffer_band). A genuinely Invalid Candidate
    must still be matched and reported invalid — not silently mislabeled non_trading,
    the exact symptom we observed."""
    # Canonical invalid key: sorted-name order -> (buffer_band=0.2, entry_band=0.0).
    invalid_keys = set(candidate_keys({"entry_band": [0.0], "buffer_band": [0.2]}))
    # Grid built in sweep/insertion order; metric all-NaN, so a pre-fix key miss would fall
    # through to non_trading.
    grid = make_candidate_grid(
        {(0.0, 0.2): {"s0": {"sharpe": None}}},
        param_names=["entry_band", "buffer_band"],
    )

    verdict = classify_candidates(grid, invalid_keys=invalid_keys, min_trades=0, metric="sharpe")

    assert verdict.invalid == {(0.2, 0.0)}
    assert verdict.non_trading == set()
    assert verdict.valid == set()


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


def test_classify_missing_ranking_metric_raises_key_error() -> None:
    grid = make_candidate_grid({("A",): {"s0": {"sharpe": 1.0}}})

    with pytest.raises(KeyError, match="not present in grid columns"):
        classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="absent")


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
