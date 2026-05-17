import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.config import (
    REPORT_STATUSES,
    DataConfig,
    ExperimentConfig,
    SplitConfig,
    load_experiment_config,
    resolve_experiment_config,
)
from research.aegis_research.experiments import run_experiment


def test_synthetic_baseline_experiment_runs(tmp_path: Path) -> None:
    config = load_experiment_config("research/configs/experiments/synthetic_ml_baseline.yaml")
    config = resolve_experiment_config(replace(config.config, output_dir=str(tmp_path)))

    result = run_experiment(config)

    run_dir = Path(result["run_dir"])
    assert (run_dir / "survival_report.json").exists()
    assert (run_dir / "config.yaml").exists()
    assert (run_dir / "config_authored.yaml").exists()
    assert (run_dir / "config_manifest.json").exists()
    assert not (run_dir / "artifacts" / "model.joblib").exists()
    assert (run_dir / "split_metrics.csv").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    artifact_ids = {artifact["id"] for artifact in manifest["artifacts"]}
    assert "data.metadata" in artifact_ids
    assert "data.native" in artifact_ids
    assert "validation.split_0.model" in artifact_ids
    assert result["report"]["validation"]["kind"] == "purged_kfold"
    assert result["report"]["validation"]["n_splits"] == 5
    assert result["report"]["status"] in REPORT_STATUSES


def test_synthetic_purged_fixlb_experiment_is_decision_grade(tmp_path: Path) -> None:
    config = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml"
    )
    config = resolve_experiment_config(replace(config.config, output_dir=str(tmp_path)))

    result = run_experiment(config, run_id="purged-fixlb")

    run_dir = Path(result["run_dir"])
    split_evidence = json.loads((run_dir / "splits" / "evidence.json").read_text())
    validation = result["report"]["validation"]

    assert validation["kind"] == "purged_kfold"
    assert validation["decision_grade"] is True
    assert validation["decision_grade_scope"] == "label_window_purging"
    assert split_evidence["purging_applied"] is True
    assert split_evidence["leakage_invariant"]["passed"] is True
    assert split_evidence["time_validation"]["pred_times_explicit"] is True
    assert split_evidence["sample_intervals"]
    assert split_evidence["sample_intervals"][0]["prediction_time"]
    assert split_evidence["sample_intervals"][0]["evaluation_time"]
    assert split_evidence["resource_estimate"]["public_artifact_bytes"] <= split_evidence[
        "resource_estimate"
    ]["max_public_artifact_bytes"]


def test_purged_public_evidence_enforces_actual_byte_cap_before_split_outputs(
    tmp_path: Path,
) -> None:
    resolved = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml"
    )
    experiment = replace(
        resolved.config,
        output_dir=str(tmp_path),
        split=replace(resolved.config.split, max_public_artifact_bytes=100),
    )
    config = resolve_experiment_config(experiment)

    with pytest.raises(ValueError, match="label evaluation evidence"):
        run_experiment(config, run_id="purged-byte-cap")

    run_dir = tmp_path / "purged-byte-cap"
    assert not (run_dir / "labels" / "evaluation_evidence.json").exists()
    assert not (run_dir / "split_metrics.csv").exists()


def test_synthetic_purged_experiment_preserves_multi_asset_axis(tmp_path: Path) -> None:
    config = load_experiment_config("research/configs/experiments/synthetic_ml_baseline.yaml")
    experiment = replace(
        config.config,
        output_dir=str(tmp_path),
        data=replace(config.config.data, symbols=["AAA", "BBB"], rows=240),
    )
    config = resolve_experiment_config(experiment)

    result = run_experiment(config)

    run_dir = Path(result["run_dir"])
    probabilities = (run_dir / "probabilities.csv").read_text()
    report = result["report"]

    assert "AAA" in probabilities
    assert "BBB" in probabilities
    assert set(report["test_metrics"]["per_symbol"]["total_return_pct"]) == {"AAA", "BBB"}


def test_purged_fixlb_runs_with_close_only_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "close_only.csv"
    close_values = [100 + (i % 30 if (i // 30) % 2 == 0 else 30 - (i % 30)) for i in range(260)]
    pd.DataFrame(
        {"Close": close_values},
        index=pd.date_range("2020-01-01", periods=260, freq="1D", tz="UTC"),
    ).to_csv(csv_path)
    config = resolve_experiment_config(
        ExperimentConfig(
            name="close-only-fixlb",
            output_dir=str(tmp_path / "runs"),
            data=DataConfig(source="csv", path=str(csv_path), symbols=["SYN"]),
            split=SplitConfig(kind="purged_kfold", n_folds=3, max_splits=3),
        )
    )

    result = run_experiment(config, run_id="close-only-run")

    assert result["status"] == "completed"
