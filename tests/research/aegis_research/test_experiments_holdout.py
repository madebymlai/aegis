import json
from dataclasses import replace
from pathlib import Path

from research.aegis_research.config import (
    REPORT_STATUSES,
    load_experiment_config,
    resolve_experiment_config,
)
from research.aegis_research.experiments import run_experiment


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
    assert "validation.holdout.model" in artifact_ids
    assert result["report"]["validation"]["kind"] == "holdout"
    assert result["report"]["validation"]["n_splits"] == 1
    assert result["report"]["status"] in REPORT_STATUSES
