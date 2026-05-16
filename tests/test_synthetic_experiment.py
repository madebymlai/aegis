from pathlib import Path

from research.aegis_research.config import load_experiment_config
from research.aegis_research.experiments import run_experiment


def test_synthetic_experiment_runs(tmp_path: Path) -> None:
    config = load_experiment_config("research/configs/experiments/synthetic_ml_baseline.yaml")
    config = config.__class__(**{**config.__dict__, "output_dir": str(tmp_path)})

    result = run_experiment(config)

    run_dir = Path(result["run_dir"])
    assert (run_dir / "survival_report.json").exists()
    assert (run_dir / "artifacts" / "model.joblib").exists()
    assert result["report"]["status"] in {"survived", "rejected", "needs_more_evidence"}
