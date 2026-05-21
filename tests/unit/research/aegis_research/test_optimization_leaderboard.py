from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS
from research.aegis_research.optimization.evidence import candidate_rows_from_param_index
from research.aegis_research.optimization.leaderboard import (
    OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION,
    build_optimization_leaderboard,
)
from research.aegis_research.optimization.runner import METRIC_INDEX_NAME


def _build_selection_series(
    winners_per_split: dict[int, tuple[int, int]],
    metric_values: dict[tuple[int, str, str], dict[str, float]],
) -> pd.Series:
    rows: list[tuple[Any, ...]] = []
    values: list[float] = []
    for split_idx, (fast, slow) in winners_per_split.items():
        for set_label in ("selection", "held_out"):
            metrics = metric_values[(split_idx, set_label, f"{fast}-{slow}")]
            for metric_name in PORTFOLIO_METRIC_VALUE_KEYS:
                rows.append((split_idx, set_label, fast, slow, metric_name))
                values.append(metrics.get(metric_name, float("nan")))
    index = pd.MultiIndex.from_tuples(
        rows,
        names=["split", "set", "fast_window", "slow_window", METRIC_INDEX_NAME],
    )
    return pd.Series(values, index=index, name="value")


def _build_candidate_rows() -> list[dict[str, Any]]:
    sampled_index = pd.MultiIndex.from_tuples(
        [(2, 10), (5, 10), (5, 20)],
        names=["fast_window", "slow_window"],
    )
    return candidate_rows_from_param_index(
        sampled_index,
        source_identity={"source": "test"},
    )


def test_leaderboard_aggregates_held_out_winners_with_candidate_keys() -> None:
    winners = {0: (2, 10), 1: (5, 10), 2: (5, 10)}
    metric_values = {
        (0, "selection", "2-10"): {"total_return": 0.10, "sharpe_ratio": 1.0},
        (0, "held_out", "2-10"): {"total_return": 0.05, "sharpe_ratio": 0.5},
        (1, "selection", "5-10"): {"total_return": 0.20, "sharpe_ratio": 1.5},
        (1, "held_out", "5-10"): {"total_return": 0.15, "sharpe_ratio": 1.2},
        (2, "selection", "5-10"): {"total_return": 0.30, "sharpe_ratio": 2.0},
        (2, "held_out", "5-10"): {"total_return": 0.25, "sharpe_ratio": 1.8},
    }
    selection = _build_selection_series(winners, metric_values)
    candidate_rows = _build_candidate_rows()
    split_held_out_row_counts = {0: 10, 1: 10, 2: 10}

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts=split_held_out_row_counts,
        ranking_metric="total_return",
        ranking_direction="desc",
        metric_registry_fingerprint="fp-test",
    )

    assert leaderboard["schema_version"] == OPTIMIZATION_LEADERBOARD_SCHEMA_VERSION
    assert leaderboard["weight_basis"] == "held_out_row_count"
    assert leaderboard["metric_registry_fingerprint"] == "fp-test"
    rows = leaderboard["rows"]
    assert len(rows) == 2, "two unique winners across 3 splits"
    top = rows[0]
    assert top["params"] == {"fast_window": 5, "slow_window": 10}
    assert top["selected_split_count"] == 2
    assert top["split_refs"] == [1, 2]
    assert math.isclose(top["ranking_metric_value"], 0.20)
    assert top["metrics"]["total_return"] == 0.20
    assert top["candidate_key"].startswith("cand_")
    assert leaderboard["summary"]["selected_splits"] == 3
    assert leaderboard["summary"]["attempted_splits"] == 3
    assert leaderboard["summary"]["unique_winner_count"] == 2

    candidate_keys = {candidate["candidate_key"] for candidate in candidate_rows}
    for row in rows:
        assert row["candidate_key"] in candidate_keys


def test_leaderboard_ascending_direction_orders_by_minimum_first() -> None:
    winners = {0: (2, 10), 1: (5, 20)}
    metric_values = {
        (0, "selection", "2-10"): {"max_dd": 0.05, "total_return": 0.1},
        (0, "held_out", "2-10"): {"max_dd": 0.02, "total_return": 0.1},
        (1, "selection", "5-20"): {"max_dd": 0.50, "total_return": 0.2},
        (1, "held_out", "5-20"): {"max_dd": 0.30, "total_return": 0.2},
    }
    selection = _build_selection_series(winners, metric_values)
    candidate_rows = _build_candidate_rows()

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10, 1: 10},
        ranking_metric="max_dd",
        ranking_direction="asc",
    )

    rows = leaderboard["rows"]
    assert [row["params"]["fast_window"] for row in rows] == [2, 5]
    assert rows[0]["ranking_metric_value"] < rows[1]["ranking_metric_value"]


def test_leaderboard_missing_winner_in_candidates_emits_failure_sample() -> None:
    winners = {0: (99, 99)}
    metric_values = {
        (0, "selection", "99-99"): {"total_return": 0.5},
        (0, "held_out", "99-99"): {"total_return": 0.4},
    }
    selection = _build_selection_series(winners, metric_values)
    candidate_rows = _build_candidate_rows()

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    assert leaderboard["rows"] == []
    assert leaderboard["failure_samples"], "missing winner should produce failure_samples"
    assert "not present in candidate evidence" in leaderboard["failure_samples"][0]["message"]


def test_leaderboard_weights_aggregate_by_held_out_row_counts() -> None:
    winners = {0: (5, 10), 1: (5, 10)}
    metric_values = {
        (0, "selection", "5-10"): {"total_return": 0.10},
        (0, "held_out", "5-10"): {"total_return": 0.10},
        (1, "selection", "5-10"): {"total_return": 0.20},
        (1, "held_out", "5-10"): {"total_return": 0.20},
    }
    selection = _build_selection_series(winners, metric_values)
    candidate_rows = _build_candidate_rows()

    leaderboard = build_optimization_leaderboard(
        selection=selection,
        candidate_rows=candidate_rows,
        split_held_out_row_counts={0: 30, 1: 10},
        ranking_metric="total_return",
        ranking_direction="desc",
    )

    row = leaderboard["rows"][0]
    expected = (0.10 * 30 + 0.20 * 10) / 40
    assert math.isclose(row["ranking_metric_value"], expected)
    assert row["held_out_row_count"] == 40
