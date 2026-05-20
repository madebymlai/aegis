from __future__ import annotations

import pytest

from research.aegis_research.run_leaderboard import build_run_leaderboard


def test_build_run_leaderboard_ranks_top_10_with_counts() -> None:
    records = [
        {
            "variant_id": f"v{i:02d}",
            "metrics": {"total_return_pct": float(i)},
            "metric_source": "central_portfolio",
        }
        for i in range(12)
    ]
    records.append({"variant_id": "failed", "error": {"code": "runtime", "message": "bad"}})

    leaderboard = build_run_leaderboard(
        records,
        metric="total_return_pct",
        direction="desc",
    )

    assert [row["variant_id"] for row in leaderboard["rows"]][:3] == ["v11", "v10", "v09"]
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


def test_build_run_leaderboard_records_source_and_baseline_delta_direction() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "better_lower_drawdown",
                "strategy_source": "playbook",
                "strategy_id": "ma_cross",
                "indicator_source": "playbook",
                "indicator_id": "ma_explore",
                "metrics": {"max_drawdown_pct": 0.1},
                "metric_source": "central_portfolio",
                "baseline_metrics": {"max_drawdown_pct": 0.2},
                "baseline_metric_source": "central_portfolio",
                "baseline_component_indicator_id": "baseline.ma",
            }
        ],
        metric="max_drawdown_pct",
        direction="asc",
        rank_by="baseline_delta",
    )

    row = leaderboard["rows"][0]
    assert row["strategy_source"] == "playbook"
    assert row["indicator_source"] == "playbook"
    assert row["primary_metric_value"] == 0.1
    assert row["baseline_metric_value"] == 0.2
    assert row["baseline_delta"] == pytest.approx(-0.1)
    assert row["direction_adjusted_delta"] == pytest.approx(0.1)


def test_baseline_delta_fallback_preserves_ascending_metric_direction() -> None:
    leaderboard = build_run_leaderboard(
        [
            {
                "variant_id": "higher_drawdown",
                "metrics": {"max_drawdown_pct": 0.4},
                "metric_source": "central_portfolio",
            },
            {
                "variant_id": "lower_drawdown",
                "metrics": {"max_drawdown_pct": 0.1},
                "metric_source": "central_portfolio",
            },
        ],
        metric="max_drawdown_pct",
        direction="asc",
        rank_by="baseline_delta",
    )

    assert [row["variant_id"] for row in leaderboard["rows"]] == [
        "lower_drawdown",
        "higher_drawdown",
    ]


def test_build_run_leaderboard_rejects_missing_metric_source() -> None:
    with pytest.raises(ValueError, match="metric source"):
        build_run_leaderboard(
            [{"variant_id": "unknown_source", "metrics": {"total_return_pct": 1.0}}],
            metric="total_return_pct",
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
                "metrics": {"total_return_pct": 1.0},
                "metric_source": "central_portfolio",
            }
        ],
        metric="total_return_pct",
        direction="desc",
    )

    row = leaderboard["rows"][0]
    assert row["composed_candidate_id"] == row["variant_id"]
    assert row["strategy_candidate_id"] == "fast"
    assert row["strategy_params"] == {"threshold": 0.0}
    assert row["indicator_candidates"] == [
        {
            "source": "playbook",
            "id": "ma",
            "candidate_id": "ma-20",
            "params": {"window": 20},
        }
    ]
