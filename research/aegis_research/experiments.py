from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from research.aegis_research.config import ExperimentConfig, to_builtin
from research.aegis_research.data import close_from_ohlcv, load_market_data
from research.aegis_research.indicators import build_indicators
from research.aegis_research.labels import _primary_close, build_labels
from research.aegis_research.models import export_model
from research.aegis_research.reports import build_survival_report, write_report
from research.aegis_research.splits import chronological_split
from research.aegis_research.validation import evaluate_holdout_split


def run_experiment(config: ExperimentConfig) -> dict[str, object]:
    run_dir = _make_run_dir(config)
    data = load_market_data(config.data)
    close = _primary_close(close_from_ohlcv(data))
    indicators = build_indicators(close, config.indicators)
    labels = build_labels(close, config.labels)
    split = chronological_split(indicators.index.intersection(labels.dropna().index), config.split)
    validation = evaluate_holdout_split(close, indicators, labels, split, config)
    report = build_survival_report(
        config.name,
        validation.train_metrics,
        validation.test_metrics,
        config.report,
    )

    export_model(validation.model, run_dir / "artifacts" / "model.joblib")
    write_report(report, run_dir / "survival_report.json")
    (run_dir / "config.yaml").write_text(yaml.safe_dump(to_builtin(asdict(config)), sort_keys=False))
    validation.probabilities.to_frame().to_csv(run_dir / "probabilities.csv")
    validation.entries.to_frame().join(validation.exits).to_csv(run_dir / "signals.csv")

    return {"run_dir": str(run_dir), "report": report}


def _make_run_dir(config: ExperimentConfig) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(config.output_dir) / f"{timestamp}_{config.name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "artifacts").mkdir()
    return run_dir
