from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.optimization import ranking
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
    select_representative_candidates,
)


def _grid(
    values_by_candidate: dict[str, dict[str, float]], *, metric: str = "sharpe"
) -> pd.DataFrame:
    """Build a tidy (param, split) grid carrying one selection-set metric column."""
    tuples: list[tuple[str, str]] = []
    rows: list[dict[str, float]] = []
    for param, by_split in values_by_candidate.items():
        for split, value in by_split.items():
            tuples.append((param, split))
            rows.append({metric: value})
    index = pd.MultiIndex.from_tuples(tuples, names=["param", "split"])
    return pd.DataFrame(rows, index=index)


def _grid_with_trades(
    spec: dict[str, dict[str, tuple[float, float]]], *, metric: str = "sharpe"
) -> pd.DataFrame:
    """Tidy (param, split) grid carrying a ``metric`` and a ``total_trades`` column.

    ``spec`` maps candidate -> split -> (metric_value, trade_count).
    """
    tuples: list[tuple[str, str]] = []
    rows: list[dict[str, float]] = []
    for param, by_split in spec.items():
        for split, (value, trades) in by_split.items():
            tuples.append((param, split))
            rows.append({metric: value, "total_trades": trades})
    index = pd.MultiIndex.from_tuples(tuples, names=["param", "split"])
    return pd.DataFrame(rows, index=index)


def test_worked_example_min_aware_penalty_ranks_steady_candidate_first() -> None:
    # Equal means (0.6) but A has a catastrophic split. Min-aware MUST rank B above A.
    grid = _grid(
        {
            "A": {"s0": 1.6, "s1": -0.4},  # mean 0.6, min -0.4 -> score 0.30
            "B": {"s0": 0.7, "s1": 0.5},  # mean 0.6, min  0.5 -> score 0.57
        }
    )

    result = select_representative_candidates(grid, metric="sharpe", min_weight=0.3)

    assert result.best.params == {"param": "B"}
    assert result.worst.params == {"param": "A"}
    assert result.best.score == pytest.approx(0.57)
    assert result.worst.score == pytest.approx(0.30)


def test_three_candidates_pick_best_median_worst_by_rank() -> None:
    grid = _grid(
        {
            "hi": {"s0": 1.0, "s1": 1.0},  # score 1.0
            "mid": {"s0": 0.5, "s1": 0.5},  # score 0.5
            "lo": {"s0": 0.1, "s1": 0.1},  # score 0.1
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    # N=3 -> median is rank ceil(3/2)=2, a real candidate distinct from best/worst.
    assert result.best.params == {"param": "hi"}
    assert result.median.params == {"param": "mid"}
    assert result.worst.params == {"param": "lo"}


def test_single_candidate_is_best_median_and_worst() -> None:
    grid = _grid({"only": {"s0": 0.3, "s1": 0.9}})

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best is result.median is result.worst
    assert result.best.params == {"param": "only"}


def test_two_candidates_median_is_one_of_them() -> None:
    grid = _grid({"x": {"s0": 1.0, "s1": 1.0}, "y": {"s0": 0.0, "s1": 0.0}})

    result = select_representative_candidates(grid, metric="sharpe")

    # N=2 -> median is rank ceil(2/2)=1, i.e. the best; still a real candidate.
    assert result.median is result.best
    assert result.median.params in ({"param": "x"}, {"param": "y"})


def test_min_weight_zero_is_pure_mean_ranking() -> None:
    # A has the higher mean but a catastrophic split; B is steadier.
    grid = _grid({"A": {"s0": 1.6, "s1": -0.4}, "B": {"s0": 0.5, "s1": 0.5}})

    result = select_representative_candidates(grid, metric="sharpe", min_weight=0.0)

    # Pure mean: A (0.6) beats B (0.5), reversing the min-aware order.
    assert result.best.params == {"param": "A"}
    assert result.best.score == pytest.approx(0.6)


def test_min_weight_one_is_pure_min_ranking() -> None:
    grid = _grid({"A": {"s0": 1.6, "s1": -0.4}, "B": {"s0": 0.7, "s1": 0.5}})

    result = select_representative_candidates(grid, metric="sharpe", min_weight=1.0)

    # Pure min: B (0.5) beats A (-0.4).
    assert result.best.params == {"param": "B"}
    assert result.best.score == pytest.approx(0.5)
    assert result.worst.score == pytest.approx(-0.4)


def test_nan_split_is_skipped_in_score_and_aggregate() -> None:
    grid = _grid(
        {
            "A": {"s0": 1.0, "s1": float("nan")},  # only s0 counts
            "B": {"s0": 0.4, "s1": 0.4},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best.params == {"param": "A"}
    assert result.best.score == pytest.approx(1.0)
    assert result.best.metrics["sharpe"] == pytest.approx(1.0)
    assert result.best.selection_metrics["s1"]["sharpe"] is None


def test_single_trading_candidate_fills_all_roles_and_excludes_dead() -> None:
    # One trading + one dead: the dead combo is excluded, so the lone trading
    # candidate fills all three roles (never the NaN-scored one).
    grid = _grid(
        {
            "good": {"s0": 0.2, "s1": 0.2},
            "blank": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best is result.median is result.worst
    assert result.best.params == {"param": "good"}
    assert result.excluded_degenerate == 1


def test_median_and_worst_skip_degenerate_candidates() -> None:
    # 3 trading candidates + 2 dead (all-NaN). best/median/worst must all be
    # drawn from the trading set; a dead combo must never occupy worst.
    grid = _grid(
        {
            "good_hi": {"s0": 1.0, "s1": 1.0},  # score 1.0
            "good_mid": {"s0": 0.5, "s1": 0.5},  # score 0.5
            "good_lo": {"s0": 0.1, "s1": 0.1},  # score 0.1
            "dead1": {"s0": float("nan"), "s1": float("nan")},
            "dead2": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best.params == {"param": "good_hi"}
    assert result.median.params == {"param": "good_mid"}
    assert result.worst.params == {"param": "good_lo"}


def test_excluded_degenerate_count_is_reported() -> None:
    # Consumers must be able to tell the grid carried dead combos.
    grid = _grid(
        {
            "good_hi": {"s0": 1.0, "s1": 1.0},
            "good_lo": {"s0": 0.1, "s1": 0.1},
            "dead1": {"s0": float("nan"), "s1": float("nan")},
            "dead2": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.excluded_degenerate == 2


def test_no_degenerate_candidates_reports_zero_excluded() -> None:
    grid = _grid({"hi": {"s0": 1.0, "s1": 1.0}, "lo": {"s0": 0.1, "s1": 0.1}})

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.excluded_degenerate == 0


def test_total_candidates_is_exact_ranked_set_size() -> None:
    # total_candidates is the EXACT count of candidates that entered ranking
    # (the ranked-set size), never a preflight sampling estimate. Four distinct
    # parameter combinations enter ranking, two of which are degenerate.
    grid = _grid(
        {
            "good_hi": {"s0": 1.0, "s1": 1.0},
            "good_lo": {"s0": 0.1, "s1": 0.1},
            "dead1": {"s0": float("nan"), "s1": float("nan")},
            "dead2": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.total_candidates == 4
    # Nesting invariant: invalid is a subset of degenerate, degenerate of total.
    assert result.excluded_invalid <= result.excluded_degenerate <= result.total_candidates


def test_all_degenerate_grid_raises_clear_error() -> None:
    # Every candidate is dead: there is no trading population to represent.
    grid = _grid(
        {
            "dead1": {"s0": float("nan"), "s1": float("nan")},
            "dead2": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    with pytest.raises(ValueError, match="finite ranking score"):
        select_representative_candidates(grid, metric="sharpe")


def test_two_trading_candidates_with_dead_combos_pick_median_from_trading() -> None:
    grid = _grid(
        {
            "x": {"s0": 1.0, "s1": 1.0},
            "y": {"s0": 0.0, "s1": 0.0},
            "dead": {"s0": float("nan"), "s1": float("nan")},
        }
    )

    result = select_representative_candidates(grid, metric="sharpe")

    # 2 trading -> median is rank ceil(2/2)=1 (the best of the trading set).
    assert result.median is result.best
    assert result.best.params == {"param": "x"}
    assert result.worst.params == {"param": "y"}
    assert result.excluded_degenerate == 1


def test_min_trades_floor_excludes_thin_high_sharpe_winner() -> None:
    # The thin candidate has the best score but won on 2-3 lucky trades/split; the
    # min-trades floor must drop it so the well-traded candidate wins instead.
    grid = _grid_with_trades(
        {
            "lucky": {"s0": (2.0, 2.0), "s1": (2.0, 3.0)},  # top score, far too few trades
            "real": {"s0": (0.6, 40.0), "s1": (0.6, 38.0)},  # lower score, plenty of trades
        }
    )

    result = select_representative_candidates(grid, metric="sharpe", min_trades=10)

    assert result.best.params == {"param": "real"}
    assert result.best.params != {"param": "lucky"}
    assert result.excluded_degenerate == 1  # the thin candidate counts as degenerate


def test_min_trades_floor_is_per_split_minimum() -> None:
    # A candidate that trades enough on one split but is thin on another fails the
    # floor: it must clear min_trades on the *thinnest* split it scored.
    grid = _grid_with_trades(
        {
            "uneven": {"s0": (3.0, 50.0), "s1": (3.0, 4.0)},  # min 4 trades -> excluded
            "steady": {"s0": (0.5, 25.0), "s1": (0.5, 30.0)},  # min 25 -> kept
        }
    )

    result = select_representative_candidates(grid, metric="sharpe", min_trades=10)

    assert result.best.params == {"param": "steady"}
    assert result.excluded_degenerate == 1


def test_min_trades_zero_is_disabled_and_needs_no_trades_column() -> None:
    # Default (min_trades=0): floor off, behaviour identical, no trades column needed.
    grid = _grid({"thin": {"s0": 2.0, "s1": 2.0}, "fat": {"s0": 0.5, "s1": 0.5}})

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best.params == {"param": "thin"}
    assert result.excluded_degenerate == 0


def test_min_trades_floor_requires_trades_column() -> None:
    grid = _grid({"a": {"s0": 1.0, "s1": 1.0}})

    with pytest.raises(KeyError, match="total_trades"):
        select_representative_candidates(grid, metric="sharpe", min_trades=10)


def test_all_candidates_under_traded_raises() -> None:
    grid = _grid_with_trades(
        {
            "a": {"s0": (2.0, 2.0), "s1": (2.0, 3.0)},
            "b": {"s0": (1.5, 1.0), "s1": (1.5, 4.0)},
        }
    )

    with pytest.raises(ValueError, match="min_trades=10"):
        select_representative_candidates(grid, metric="sharpe", min_trades=10)


def test_min_trades_floor_combines_with_nan_score_exclusion() -> None:
    # Both exclusion classes (NaN-score and under-traded) fold into excluded_degenerate.
    grid = _grid_with_trades(
        {
            "real": {"s0": (0.6, 40.0), "s1": (0.6, 40.0)},
            "thin": {"s0": (2.0, 2.0), "s1": (2.0, 2.0)},  # under-traded
            "dead": {"s0": (float("nan"), 0.0), "s1": (float("nan"), 0.0)},  # NaN score
        }
    )

    result = select_representative_candidates(grid, metric="sharpe", min_trades=10)

    assert result.best.params == {"param": "real"}
    assert result.excluded_degenerate == 2


def test_tied_scores_keep_parameter_sorted_order() -> None:
    grid = _grid({"b": {"s0": 0.5, "s1": 0.5}, "a": {"s0": 0.5, "s1": 0.5}})

    result = select_representative_candidates(grid, metric="sharpe")

    # Equal scores: stable order follows parameter-sorted grouping ("a" before "b").
    assert result.best.params == {"param": "a"}
    assert result.worst.params == {"param": "b"}


def test_all_registered_metrics_are_carried_per_split_and_aggregated() -> None:
    index = pd.MultiIndex.from_tuples([("A", "s0"), ("A", "s1")], names=["param", "split"])
    grid = pd.DataFrame({"sharpe": [1.0, 0.5], "max_drawdown": [-0.2, -0.4]}, index=index)

    result = select_representative_candidates(grid, metric="sharpe")
    candidate = result.best

    assert candidate.metrics["sharpe"] == pytest.approx(0.75)
    assert candidate.metrics["max_drawdown"] == pytest.approx(-0.3)
    assert candidate.selection_metrics["s0"] == {"sharpe": 1.0, "max_drawdown": -0.2}


def test_held_out_metrics_start_empty() -> None:
    grid = _grid({"only": {"s0": 0.3, "s1": 0.9}})

    candidate = select_representative_candidates(grid, metric="sharpe").best

    assert candidate.held_out_metrics == {}


def test_supports_multiple_parameter_levels() -> None:
    index = pd.MultiIndex.from_tuples(
        [(2, 10, "s0"), (2, 10, "s1"), (5, 20, "s0"), (5, 20, "s1")],
        names=["fast_window", "slow_window", "split"],
    )
    grid = pd.DataFrame({"sharpe": [0.9, 0.9, 0.1, 0.1]}, index=index)

    result = select_representative_candidates(grid, metric="sharpe")

    assert result.best.params == {"fast_window": 2, "slow_window": 10}


def test_evaluated_candidate_has_no_legacy_winner_or_direction_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(EvaluatedCandidate)}

    assert field_names == {
        "params",
        "score",
        "selection_metrics",
        "metrics",
        "held_out_metrics",
    }
    for forbidden in ("ranking_direction", "split_refs", "winner"):
        assert forbidden not in field_names


def test_optimization_result_has_best_median_worst_and_excluded_count() -> None:
    field_names = [f.name for f in dataclasses.fields(OptimizationResult)]

    assert field_names == [
        "best",
        "median",
        "worst",
        "excluded_degenerate",
        "excluded_invalid",
        "total_candidates",
    ]


def test_signature_has_no_direction_parameter() -> None:
    params = inspect.signature(select_representative_candidates).parameters

    assert list(params) == ["grid", "metric", "min_weight", "min_trades", "trades_metric"]
    assert params["min_weight"].default == 0.3
    assert params["min_trades"].default == 0
    assert params["trades_metric"].default == "total_trades"
    assert "direction" not in params


def test_ranking_module_imports_no_vbt_or_leaderboard() -> None:
    source = Path(ranking.__file__).read_text()

    assert "vectorbtpro" not in source
    assert "import vbt" not in source
    assert "leaderboard" not in source
    assert "build_optimization_leaderboard" not in source
