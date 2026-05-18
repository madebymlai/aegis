from __future__ import annotations

import json

import pytest

from research.aegis_research.play_artifacts import (
    PlayArtifactError,
    PlayArtifactStore,
    build_play_leaderboard,
)


def test_build_play_leaderboard_ranks_top_10_with_counts() -> None:
    records = [
        {"variant_id": f"v{i:02d}", "metrics": {"total_return_pct": float(i)}}
        for i in range(12)
    ]
    records.append({"variant_id": "failed", "error": {"code": "runtime", "message": "bad"}})

    leaderboard = build_play_leaderboard(
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


def test_build_play_leaderboard_records_baseline_delta_direction() -> None:
    leaderboard = build_play_leaderboard(
        [
            {
                "variant_id": "better_lower_drawdown",
                "metrics": {"max_drawdown_pct": 0.1},
                "baseline_metrics": {"max_drawdown_pct": 0.2},
                "baseline_component_indicator_id": "baseline.ma",
            }
        ],
        metric="max_drawdown_pct",
        direction="asc",
        rank_by="baseline_delta",
    )

    row = leaderboard["rows"][0]
    assert row["primary_metric_value"] == 0.1
    assert row["baseline_metric_value"] == 0.2
    assert row["baseline_delta"] == pytest.approx(-0.1)
    assert row["direction_adjusted_delta"] == pytest.approx(0.1)


def test_baseline_delta_fallback_preserves_ascending_metric_direction() -> None:
    leaderboard = build_play_leaderboard(
        [
            {"variant_id": "higher_drawdown", "metrics": {"max_drawdown_pct": 0.4}},
            {"variant_id": "lower_drawdown", "metrics": {"max_drawdown_pct": 0.1}},
        ],
        metric="max_drawdown_pct",
        direction="asc",
        rank_by="baseline_delta",
    )

    assert [row["variant_id"] for row in leaderboard["rows"]] == [
        "lower_drawdown",
        "higher_drawdown",
    ]


def test_play_artifact_success_writes_last_run_and_replaces_after_validation(tmp_path) -> None:
    store = PlayArtifactStore(tmp_path)
    first = store.write_success(
        play_name="first",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "first", "metrics": {"total_return_pct": 1.0}}],
    )

    second = store.write_success(
        play_name="second",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "second", "metrics": {"total_return_pct": 2.0}}],
    )

    summary = json.loads((tmp_path / "play" / "last-run" / "summary.json").read_text())
    assert first["last_run_dir"] == str(tmp_path / "play" / "last-run")
    assert second["last_run_dir"] == str(tmp_path / "play" / "last-run")
    assert summary["play_name"] == "second"
    assert summary["leaderboard_summary"]["succeeded"] == 1


def test_play_artifact_backup_preserves_prior_completed_last_run(tmp_path) -> None:
    store = PlayArtifactStore(tmp_path)
    store.write_success(
        play_name="first",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "first", "metrics": {"total_return_pct": 1.0}}],
    )

    result = store.write_success(
        play_name="second",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "second", "metrics": {"total_return_pct": 2.0}}],
        backup=True,
    )

    backup_dir = result["backup_dir"]
    assert backup_dir is not None
    backup_summary = json.loads((tmp_path / backup_dir / "summary.json").read_text())
    assert backup_summary["play_name"] == "first"


def test_failed_play_attempt_does_not_replace_previous_last_run(tmp_path) -> None:
    store = PlayArtifactStore(tmp_path)
    store.write_success(
        play_name="successful",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "winner", "metrics": {"total_return_pct": 1.0}}],
    )

    with pytest.raises(PlayArtifactError):
        store.write_success(
            play_name="failed",
            ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
            variant_records=[{"variant_id": "bad", "metrics": {"total_return_pct": None}}],
        )

    summary = json.loads((tmp_path / "play" / "last-run" / "summary.json").read_text())
    assert summary["play_name"] == "successful"
    failure = store.write_failed_attempt("failed", RuntimeError("private /tmp/path token=secret"))
    failure_summary = json.loads((tmp_path / failure["failure_path"]).read_text())
    assert "<tmp>" in failure_summary["message"]
    assert "token=" not in failure_summary["message"]


def test_play_artifact_success_rejects_unsafe_public_payload(tmp_path) -> None:
    store = PlayArtifactStore(tmp_path)

    with pytest.raises(PlayArtifactError, match="unsafe public metadata"):
        store.write_success(
            play_name="unsafe",
            ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
            variant_records=[
                {
                    "variant_id": "winner",
                    "metrics": {"total_return_pct": 1.0},
                    "params": {"api_token": "super-secret-token"},
                }
            ],
        )

    assert not (tmp_path / "play" / "last-run").exists()


def test_failed_last_run_publish_restores_previous_success(tmp_path, monkeypatch) -> None:
    store = PlayArtifactStore(tmp_path)
    store.write_success(
        play_name="successful",
        ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
        variant_records=[{"variant_id": "winner", "metrics": {"total_return_pct": 1.0}}],
    )
    original_replace = type(tmp_path).replace

    def failing_replace(self, target):
        if self.parent.name == ".staging" and target == tmp_path / "play" / "last-run":
            raise RuntimeError("publish failed")
        return original_replace(self, target)

    monkeypatch.setattr(type(tmp_path), "replace", failing_replace)

    with pytest.raises(RuntimeError, match="publish failed"):
        store.write_success(
            play_name="failed_publish",
            ranking={"metric": "total_return_pct", "direction": "desc", "rank_by": "primary_metric"},
            variant_records=[{"variant_id": "new", "metrics": {"total_return_pct": 2.0}}],
        )

    summary = json.loads((tmp_path / "play" / "last-run" / "summary.json").read_text())
    assert summary["play_name"] == "successful"
