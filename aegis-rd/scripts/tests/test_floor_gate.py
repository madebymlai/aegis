from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from scripts.floor_evaluation import (
    FloorEvaluationError,
    FloorEvaluationSettings,
    evaluate_floor_pair,
    load_locked_strategy_returns,
)


def test_floor_pair_uses_realized_config_returns_at_declared_weight() -> None:
    index = pd.date_range("2020-01-31", periods=24, freq="ME")
    trend = pd.Series([0.01] * 24, index=index, name="trend")
    carry = pd.Series([0.03] * 24, index=index, name="carry")

    report = evaluate_floor_pair(
        trend,
        carry,
        settings=FloorEvaluationSettings(
            carry_weight=0.40,
            bootstrap_samples=100,
            block_lengths=(1,),
            seed=7,
        ),
    )

    assert report["comparison"]["composite"]["monthly_mean"] == pytest.approx(0.018)
    assert report["comparison"]["trend_only"]["monthly_mean"] == pytest.approx(0.01)


def test_floor_pair_joint_bootstrap_is_seeded_and_reports_block_sensitivity() -> None:
    index = pd.date_range("2018-01-31", periods=48, freq="ME")
    trend = pd.Series(np.tile([0.02, -0.01, 0.01, 0.00], 12), index=index)
    carry = pd.Series(np.tile([0.01, 0.01, -0.02, 0.02], 12), index=index)
    settings = FloorEvaluationSettings(
        bootstrap_samples=200,
        block_lengths=(1, 3, 6),
        seed=42,
    )

    first = evaluate_floor_pair(trend, carry, settings=settings)
    second = evaluate_floor_pair(trend, carry, settings=settings)

    assert first["bootstrap"] == second["bootstrap"]
    assert [row["block_length_months"] for row in first["bootstrap"]] == [1, 3, 6]


def test_floor_pair_rejects_non_overlapping_return_histories() -> None:
    trend = pd.Series([0.01, 0.02], index=pd.date_range("2020-01-31", periods=2, freq="ME"))
    carry = pd.Series([0.01, 0.02], index=pd.date_range("2021-01-31", periods=2, freq="ME"))

    try:
        evaluate_floor_pair(trend, carry)
    except ValueError as error:
        message = str(error)
    else:
        raise AssertionError("expected non-overlapping histories to be rejected")

    assert message == "trend and carry returns have no common observations"


def test_floor_gate_requires_trend_and_carry_config_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "scripts/floor_gate.py"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--trend" in result.stderr
    assert "--carry" in result.stderr


def test_floor_gate_rejects_an_unlocked_experiment_before_loading_data(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source = repo_root / "research/configs/demeter/credit_bucket.yaml"
    authored = yaml.safe_load(source.read_text())
    del authored["lock"]
    unlocked = tmp_path / "unlocked.yaml"
    unlocked.write_text(yaml.safe_dump(authored, sort_keys=False))

    with pytest.raises(FloorEvaluationError) as exc_info:
        load_locked_strategy_returns(unlocked)

    assert "has no top-level lock" in str(exc_info.value)
