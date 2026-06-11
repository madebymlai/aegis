from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from research.aegis_research.optimization import ranking
from research.aegis_research.optimization.candidate_grid import CandidateGrid
from research.aegis_research.optimization.candidate_validity import (
    Verdicts,
    classify_candidates,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
    select_representative_candidates,
)
from tests.support.research.aegis_research.factories import make_candidate_grid


def _grid(
    values_by_candidate: dict[str, dict[str, float]], *, metric: str = "sharpe"
) -> CandidateGrid:
    """Build a CandidateGrid carrying one selection-set metric column."""
    return make_candidate_grid({
        (key,): {s: {metric: v} for s, v in splits.items()}
        for key, splits in values_by_candidate.items()
    })


def _all_valid_verdict(
    values_by_candidate: dict[str, dict[str, float]], *, metric: str = "sharpe"
) -> Verdicts:
    """Build a verdict where every candidate is valid, using the factory."""
    grid = _grid(values_by_candidate, metric=metric)
    return classify_candidates(grid, invalid_keys=set(), min_trades=0, metric=metric)


# ---------------------------------------------------------------------------
# Pure ranking (all-valid verdict)
# ---------------------------------------------------------------------------


def test_worked_example_min_aware_penalty_ranks_steady_candidate_first() -> None:
    # Equal means (0.6) but A has a catastrophic split. Min-aware MUST rank B above A.
    candidates = {"A": {"s0": 1.6, "s1": -0.4}, "B": {"s0": 0.7, "s1": 0.5}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe", min_weight=0.3)

    assert result.best.params == {"param": "B"}
    assert result.worst.params == {"param": "A"}
    assert result.best.score == pytest.approx(0.57)
    assert result.worst.score == pytest.approx(0.30)


def test_three_candidates_pick_best_median_worst_by_rank() -> None:
    candidates = {"hi": {"s0": 1.0, "s1": 1.0}, "mid": {"s0": 0.5, "s1": 0.5}, "lo": {"s0": 0.1, "s1": 0.1}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    # N=3 -> median is rank ceil(3/2)=2, a real candidate distinct from best/worst.
    assert result.best.params == {"param": "hi"}
    assert result.median.params == {"param": "mid"}
    assert result.worst.params == {"param": "lo"}


def test_single_candidate_is_best_median_and_worst() -> None:
    candidates = {"only": {"s0": 0.3, "s1": 0.9}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.best is result.median is result.worst
    assert result.best.params == {"param": "only"}


def test_two_candidates_median_is_one_of_them() -> None:
    candidates = {"x": {"s0": 1.0, "s1": 1.0}, "y": {"s0": 0.0, "s1": 0.0}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    # N=2 -> median is rank ceil(2/2)=1, i.e. the best; still a real candidate.
    assert result.median is result.best
    assert result.median.params in ({"param": "x"}, {"param": "y"})


def test_min_weight_zero_is_pure_mean_ranking() -> None:
    # A has the higher mean but a catastrophic split; B is steadier.
    candidates = {"A": {"s0": 1.6, "s1": -0.4}, "B": {"s0": 0.5, "s1": 0.5}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe", min_weight=0.0)

    # Pure mean: A (0.6) beats B (0.5), reversing the min-aware order.
    assert result.best.params == {"param": "A"}
    assert result.best.score == pytest.approx(0.6)


def test_min_weight_one_is_pure_min_ranking() -> None:
    candidates = {"A": {"s0": 1.6, "s1": -0.4}, "B": {"s0": 0.7, "s1": 0.5}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe", min_weight=1.0)

    # Pure min: B (0.5) beats A (-0.4).
    assert result.best.params == {"param": "B"}
    assert result.best.score == pytest.approx(0.5)
    assert result.worst.score == pytest.approx(-0.4)


def test_nan_split_is_skipped_in_score_and_aggregate() -> None:
    candidates = {"A": {"s0": 1.0, "s1": float("nan")}, "B": {"s0": 0.4, "s1": 0.4}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.best.params == {"param": "A"}
    assert result.best.score == pytest.approx(1.0)
    assert result.best.metrics["sharpe"] == pytest.approx(1.0)
    assert result.best.selection_metrics["s1"]["sharpe"] is None


def test_tied_scores_keep_parameter_sorted_order() -> None:
    candidates = {"b": {"s0": 0.5, "s1": 0.5}, "a": {"s0": 0.5, "s1": 0.5}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    # Equal scores: stable order follows parameter-sorted grouping ("a" before "b").
    assert result.best.params == {"param": "a"}
    assert result.worst.params == {"param": "b"}


def test_all_registered_metrics_are_carried_per_split_and_aggregated() -> None:
    grid = make_candidate_grid({
        ("A",): {"s0": {"sharpe": 1.0, "max_drawdown": -0.2}, "s1": {"sharpe": 0.5, "max_drawdown": -0.4}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")
    candidate = result.best

    assert candidate.metrics["sharpe"] == pytest.approx(0.75)
    assert candidate.metrics["max_drawdown"] == pytest.approx(-0.3)
    assert candidate.selection_metrics["s0"] == {"sharpe": 1.0, "max_drawdown": -0.2}


def test_held_out_metrics_start_empty() -> None:
    candidates = {"only": {"s0": 0.3, "s1": 0.9}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    candidate = select_representative_candidates(grid, verdict, metric="sharpe").best

    assert candidate.held_out_metrics == {}


def test_supports_multiple_parameter_levels() -> None:
    grid = make_candidate_grid(
        {
            (2, 10): {"s0": {"sharpe": 0.9}, "s1": {"sharpe": 0.9}},
            (5, 20): {"s0": {"sharpe": 0.1}, "s1": {"sharpe": 0.1}},
        },
        param_names=["fast_window", "slow_window"],
    )
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.best.params == {"fast_window": 2, "slow_window": 10}


# ---------------------------------------------------------------------------
# Ranking with excluded candidates via verdict
# ---------------------------------------------------------------------------


def test_single_trading_candidate_fills_all_roles_and_excludes_dead() -> None:
    # One trading + one dead: the dead combo is excluded by the verdict, so the
    # lone trading candidate fills all three roles (never the NaN-scored one).
    grid = make_candidate_grid({
        ("good",): {"s0": {"sharpe": 0.2}, "s1": {"sharpe": 0.2}},
        ("blank",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.best is result.median is result.worst
    assert result.best.params == {"param": "good"}
    assert result.excluded_degenerate == 1


def test_median_and_worst_skip_degenerate_candidates() -> None:
    # 3 trading candidates + 2 dead (all-NaN). best/median/worst must all be
    # drawn from the trading set; a dead combo must never occupy worst.
    grid = make_candidate_grid({
        ("good_hi",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("good_mid",): {"s0": {"sharpe": 0.5}, "s1": {"sharpe": 0.5}},
        ("good_lo",): {"s0": {"sharpe": 0.1}, "s1": {"sharpe": 0.1}},
        ("dead1",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
        ("dead2",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.best.params == {"param": "good_hi"}
    assert result.median.params == {"param": "good_mid"}
    assert result.worst.params == {"param": "good_lo"}


def test_excluded_degenerate_count_is_reported() -> None:
    # Consumers must be able to tell the grid carried dead combos.
    grid = make_candidate_grid({
        ("good_hi",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("good_lo",): {"s0": {"sharpe": 0.1}, "s1": {"sharpe": 0.1}},
        ("dead1",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
        ("dead2",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.excluded_degenerate == 2


def test_no_degenerate_candidates_reports_zero_excluded() -> None:
    candidates = {"hi": {"s0": 1.0, "s1": 1.0}, "lo": {"s0": 0.1, "s1": 0.1}}
    grid = _grid(candidates)
    verdict = _all_valid_verdict(candidates)

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.excluded_degenerate == 0


def test_total_candidates_is_exact_classified_set_size() -> None:
    # total_candidates is the EXACT count of candidates that were classified
    # (sourced from the verdict partition). Four distinct parameter combinations
    # enter classification, two of which are degenerate.
    grid = make_candidate_grid({
        ("good_hi",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("good_lo",): {"s0": {"sharpe": 0.1}, "s1": {"sharpe": 0.1}},
        ("dead1",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
        ("dead2",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    assert result.total_candidates == 4
    # Nesting invariant: invalid is a subset of degenerate, degenerate of total.
    assert result.excluded_invalid <= result.excluded_degenerate <= result.total_candidates


def test_all_degenerate_grid_raises_clear_error() -> None:
    # Every candidate is dead: there is no admissible population to represent.
    grid = make_candidate_grid({
        ("dead1",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
        ("dead2",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    with pytest.raises(ValueError, match="no admissible candidate"):
        select_representative_candidates(grid, verdict, metric="sharpe")


def test_two_trading_candidates_with_dead_combos_pick_median_from_trading() -> None:
    grid = make_candidate_grid({
        ("x",): {"s0": {"sharpe": 1.0}, "s1": {"sharpe": 1.0}},
        ("y",): {"s0": {"sharpe": 0.0}, "s1": {"sharpe": 0.0}},
        ("dead",): {"s0": {"sharpe": None}, "s1": {"sharpe": None}},
    })
    verdict = classify_candidates(grid, invalid_keys=set(), min_trades=0, metric="sharpe")

    result = select_representative_candidates(grid, verdict, metric="sharpe")

    # 2 trading -> median is rank ceil(2/2)=1 (the best of the trading set).
    assert result.median is result.best
    assert result.best.params == {"param": "x"}
    assert result.worst.params == {"param": "y"}
    assert result.excluded_degenerate == 1


# ---------------------------------------------------------------------------
# Structure / signature
# ---------------------------------------------------------------------------


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
        "non_executable_rows",
    ]


def test_signature_has_no_direction_parameter() -> None:
    params = inspect.signature(select_representative_candidates).parameters

    assert list(params) == ["grid", "verdicts", "metric", "min_weight"]
    assert params["min_weight"].default == 0.3
    assert "min_trades" not in params
    assert "trades_metric" not in params
    assert "direction" not in params


def test_ranking_module_imports_no_vbt_or_leaderboard() -> None:
    source = Path(ranking.__file__).read_text()

    assert "vectorbtpro" not in source
    assert "import vbt" not in source
    assert "leaderboard" not in source
    assert "build_optimization_leaderboard" not in source


def test_ranking_module_imports_no_pandas() -> None:
    """The ranking module went pandas-free in aegis-rd-vlw.2."""
    source = Path(ranking.__file__).read_text()

    assert "import pandas" not in source
    assert "from pandas" not in source
    assert "pd." not in source
