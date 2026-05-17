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
from research.aegis_research.data import MarketDataQualityError
from research.aegis_research.experiments import run_experiment
from research.aegis_research.models import TargetModelCompatibilityError
from research.aegis_research.provenance.manifest import ArtifactStatus, validate_manifest


def test_synthetic_holdout_experiment_runs(tmp_path: Path) -> None:
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
    assert "validation.holdout.model" in artifact_ids
    assert result["report"]["validation"]["kind"] == "holdout"
    assert result["report"]["validation"]["n_splits"] == 1
    assert result["report"]["status"] in REPORT_STATUSES


def test_synthetic_holdout_experiment_preserves_multi_asset_axis(tmp_path: Path) -> None:
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


def test_holdout_fixlb_runs_with_close_only_csv(tmp_path: Path) -> None:
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
            split=SplitConfig(diagnostic_validation_allowed=True),
        )
    )

    result = run_experiment(config, run_id="close-only-run")

    assert result["status"] == "completed"


def test_trendlb_close_only_csv_fails_data_preflight(tmp_path: Path) -> None:
    csv_path = tmp_path / "close_only.csv"
    close_values = [100 + (i % 30 if (i // 30) % 2 == 0 else 30 - (i % 30)) for i in range(260)]
    pd.DataFrame(
        {"Close": close_values},
        index=pd.date_range("2020-01-01", periods=260, freq="1D", tz="UTC"),
    ).to_csv(csv_path)
    config = resolve_experiment_config(
        {
            "schema_version": 2,
            "name": "close-only-trendlb",
            "output_dir": str(tmp_path / "runs"),
            "data": {"source": "csv", "path": str(csv_path), "symbols": ["SYN"]},
            "labels": {"generator": {"kind": "trendlb"}},
        }
    )

    with pytest.raises(MarketDataQualityError):
        run_experiment(config, run_id="close-only-trendlb-run")

    run_dir = tmp_path / "runs" / "close-only-trendlb-run"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(manifest, run_dir=run_dir)
    artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
    artifact_ids = {artifact["id"] for artifact in manifest["artifacts"]}
    data_metadata = json.loads((run_dir / "data_metadata.json").read_text())

    assert manifest["run"]["status"] == "failed"
    assert "data.metadata" in artifact_ids
    assert artifacts["data.metadata"]["status"] == ArtifactStatus.COMPLETED
    assert "data.native" not in artifact_ids
    assert data_metadata["quality"]["state"] == "rejected"


def test_unpurged_label_validation_requires_diagnostic_opt_in(tmp_path: Path) -> None:
    resolved = load_experiment_config("research/configs/experiments/synthetic_ml_baseline.yaml")
    experiment = replace(
        resolved.config,
        output_dir=str(tmp_path),
        split=replace(resolved.config.split, diagnostic_validation_allowed=False),
    )
    config = resolve_experiment_config(experiment)

    with pytest.raises(TargetModelCompatibilityError, match="diagnostic_validation_allowed"):
        run_experiment(config, run_id="unpurged-fails-closed")

    run_dir = tmp_path / "unpurged-fails-closed"
    compatibility = json.loads((run_dir / "labels" / "compatibility.json").read_text())
    manifest = json.loads((run_dir / "manifest.json").read_text())

    assert compatibility["compatible"] is False
    assert compatibility["diagnostic_validation_allowed"] is False
    assert "diagnostic_validation_allowed" in compatibility["failure_reason"]
    assert not (run_dir / "split_metrics.csv").exists()
    assert manifest["run"]["status"] == "failed"
