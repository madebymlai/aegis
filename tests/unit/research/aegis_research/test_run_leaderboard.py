from __future__ import annotations

import pytest

from research.aegis_research.run_leaderboard import build_run_leaderboard
from research.aegis_research.split_leaderboard import build_split_leaderboard


def test_build_run_leaderboard_ranks_top_10_with_counts() -> None:
    records = [
        {
            "variant_id": f"v{i:02d}",
            "metrics": {"total_return": float(i)},
            "metric_source": "central_portfolio",
        }
        for i in range(12)
    ]
    records.append({"variant_id": "failed", "error": {"code": "runtime", "message": "bad"}})

    leaderboard = build_run_leaderboard(
        records,
        metric="total_return",
        direction="desc",
    )

    assert leaderboard["primary_metric"] == "total_return"
    assert leaderboard["secondary_metrics"] == []
    assert [row["variant_id"] for row in leaderboard["rows"]][:3] == ["v11", "v10", "v09"]
    assert leaderboard["rows"][0]["metrics"]["total_return"] == 11.0
    assert len(leaderboard["rows"]) == 10
    assert leaderboard["summary"] == {
        "attempted": 13,
        "succeeded": 12,
        "failed": 1,
        "excluded": 0,
        "success_ratio": pytest.approx(12 / 13),
        "partial_leaderboard": True,
        "failure_gating_status": "partial",
    }
    assert leaderboard["failure_samples"][0]["variant_id"] == "failed"


def test_build_run_leaderboard_records_source_and_baseline_delta() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "better_lower_drawdown",
                "strategy_source": "playbook",
                "strategy_id": "ma_cross",
                "indicator_source": "playbook",
                "indicator_id": "ma_explore",
                "metrics": {"max_dd": 0.1},
                "metric_source": "central_portfolio",
                "baseline_metrics": {"max_dd": 0.2},
                "baseline_metric_source": "central_portfolio",
                "baseline_component_indicator_id": "baseline.ma",
            }
        ],
        metric="max_dd",
        direction="asc",
        secondary_metrics=["baseline_delta"],
    )

    row = leaderboard["rows"][0]
    assert row["strategy_source"] == "playbook"
    assert row["indicator_source"] == "playbook"
    assert row["metrics"]["max_dd"] == 0.1
    assert row["metrics"]["baseline_delta"] == pytest.approx(-0.1)
    assert row["baseline_metric_value"] == 0.2
    assert row["direction_adjusted_delta"] == pytest.approx(0.1)


def test_baseline_delta_fallback_preserves_ascending_metric_direction() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "higher_drawdown",
                "metrics": {"max_dd": 0.4, "sharpe_ratio": 2.0},
                "metric_source": "central_portfolio",
            },
            {
                "variant_id": "lower_drawdown",
                "metrics": {"max_dd": 0.1, "sharpe_ratio": 1.0},
                "metric_source": "central_portfolio",
            },
        ],
        metric="max_dd",
        direction="asc",
        secondary_metrics=["sharpe_ratio"],
    )

    assert [row["variant_id"] for row in leaderboard["rows"]] == [
        "lower_drawdown",
        "higher_drawdown",
    ]


def test_build_run_leaderboard_rejects_missing_metric_source() -> None:
    with pytest.raises(ValueError, match="metric source"):
        build_run_leaderboard(
            [{"variant_id": "unknown_source", "metrics": {"total_return": 1.0}}],
            metric="total_return",
            direction="desc",
        )


def test_build_run_leaderboard_preserves_composed_candidate_provenance() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "strategy:playbook:ma_cross:fast+indicators:[playbook:ma:ma-20]",
                "composed_candidate_id": "strategy:playbook:ma_cross:fast+indicators:[playbook:ma:ma-20]",
                "strategy_source": "playbook",
                "strategy_id": "ma_cross",
                "strategy_candidate_id": "fast",
                "strategy_params": {"threshold": 0.0},
                "indicator_candidates": [
                    {
                        "source": "playbook",
                        "id": "ma",
                        "candidate_id": "ma-20",
                        "params": {"window": 20},
                    }
                ],
                "metrics": {"total_return": 1.0, "sharpe_ratio": 2.0},
                "metric_source": "central_portfolio",
            }
        ],
        metric="total_return",
        direction="desc",
        secondary_metrics=["sharpe_ratio"],
        metric_registry_fingerprint="abc123",
    )

    row = leaderboard["rows"][0]
    assert leaderboard["metric_registry_fingerprint"] == "abc123"
    assert row["composed_candidate_id"] == row["variant_id"]
    assert row["strategy_candidate_id"] == "fast"
    assert row["strategy_params"] == {"threshold": 0.0}
    assert row["metrics"] == {"total_return": 1.0, "sharpe_ratio": 2.0}
    assert row["indicator_candidates"] == [
        {
            "source": "playbook",
            "id": "ma",
            "candidate_id": "ma-20",
            "params": {"window": 20},
        }
    ]


def test_build_run_leaderboard_requires_selected_secondary_metric() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "missing_secondary",
                "metrics": {"total_return": 1.0},
                "metric_source": "central_portfolio",
            }
        ],
        metric="total_return",
        direction="desc",
        secondary_metrics=["sharpe_ratio"],
    )

    assert leaderboard["rows"] == []
    assert leaderboard["summary"]["excluded"] == 1
    assert "sharpe_ratio" in leaderboard["failure_samples"][0]["message"]


def test_build_split_leaderboard_selects_only_from_selection_window() -> None:
    leaderboard = build_split_leaderboard(
        [
            _rolling_metric("split_0", "selection", "candidate_a", 2.0, 10),
            _rolling_metric("split_0", "selection", "candidate_b", 1.0, 10),
            _rolling_metric("split_0", "held_out", "candidate_a", 0.1, 5),
            _rolling_metric("split_0", "held_out", "candidate_b", 99.0, 5),
        ],
        {
            "candidate_a": {"variant_id": "candidate_a", "metric_source": "central_portfolio"},
            "candidate_b": {"variant_id": "candidate_b", "metric_source": "central_portfolio"},
        },
        metric="total_return",
        direction="desc",
    )

    assert [row["variant_id"] for row in leaderboard["rows"]] == ["candidate_a"]
    assert leaderboard["rows"][0]["metrics"]["total_return"] == pytest.approx(0.1)
    assert leaderboard["summary"]["failure_gating_status"] == "pass"


def test_build_split_leaderboard_honors_ascending_selection_direction() -> None:
    leaderboard = build_split_leaderboard(
        [
            _rolling_metric("split_0", "selection", "candidate_a", 1.0, 10),
            _rolling_metric("split_0", "selection", "candidate_b", 2.0, 10),
            _rolling_metric("split_0", "held_out", "candidate_a", 3.0, 5),
            _rolling_metric("split_0", "held_out", "candidate_b", 0.1, 5),
        ],
        {
            "candidate_a": {"variant_id": "candidate_a", "metric_source": "central_portfolio"},
            "candidate_b": {"variant_id": "candidate_b", "metric_source": "central_portfolio"},
        },
        metric="total_return",
        direction="asc",
    )

    assert [row["variant_id"] for row in leaderboard["rows"]] == ["candidate_a"]
    assert leaderboard["rows"][0]["metrics"]["total_return"] == pytest.approx(3.0)


def test_build_split_leaderboard_weights_oos_metrics_and_records_coverage() -> None:
    leaderboard = build_split_leaderboard(
        [
            _rolling_metric("split_0", "selection", "candidate_a", 2.0, 10),
            _rolling_metric("split_0", "selection", "candidate_b", 1.0, 10),
            _rolling_metric("split_0", "held_out", "candidate_a", 1.0, 1),
            _rolling_metric("split_0", "held_out", "candidate_b", 4.0, 1),
            _rolling_metric("split_1", "selection", "candidate_a", 3.0, 10),
            _rolling_metric("split_1", "selection", "candidate_b", 2.0, 10),
            _rolling_metric("split_1", "held_out", "candidate_a", 3.0, 3),
            _rolling_metric("split_1", "held_out", "candidate_b", 5.0, 3),
        ],
        {
            "candidate_a": {"variant_id": "candidate_a", "metric_source": "central_portfolio"},
            "candidate_b": {"variant_id": "candidate_b", "metric_source": "central_portfolio"},
        },
        metric="total_return",
        direction="desc",
        metric_registry_fingerprint="metrics123",
    )

    row = leaderboard["rows"][0]
    assert leaderboard["metric_registry_fingerprint"] == "metrics123"
    assert row["variant_id"] == "candidate_a"
    assert row["metrics"]["total_return"] == pytest.approx(2.5)
    assert row["selected_split_count"] == 2
    assert row["eligible_split_count"] == 2
    assert row["held_out_row_count"] == 4
    assert row["split_refs"] == ["split_0", "split_1"]


def test_build_split_leaderboard_marks_missing_selected_oos_metric_partial() -> None:
    leaderboard = build_split_leaderboard(
        [
            _rolling_metric("split_0", "selection", "candidate_a", 2.0, 10),
            _rolling_metric("split_0", "held_out", "candidate_a", None, 5),
        ],
        {"candidate_a": {"variant_id": "candidate_a", "metric_source": "central_portfolio"}},
        metric="total_return",
        direction="desc",
    )

    assert leaderboard["rows"] == []
    assert leaderboard["summary"]["partial_leaderboard"] is True
    assert "unavailable" in leaderboard["failure_samples"][0]["message"]


def _rolling_metric(
    split: str,
    set_name: str,
    candidate_id: str,
    value: float | None,
    row_count: int,
) -> dict[str, object]:
    return {
        "split_label": split,
        "set": set_name,
        "candidate_id": candidate_id,
        "row_count": row_count,
        "metric_source": "central_portfolio",
        "metrics": {"total_return": value},
    }
