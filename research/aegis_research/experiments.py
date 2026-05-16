from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from research.aegis_research.config import (
    ExperimentConfig,
    ResolvedExperimentConfig,
    resolve_experiment_config,
)
from research.aegis_research.data import (
    close_from_ohlcv,
    high_from_ohlcv,
    load_market_data,
    low_from_ohlcv,
)
from research.aegis_research.indicators import build_indicators
from research.aegis_research.labels import _primary_close, build_labels
from research.aegis_research.models import export_model
from research.aegis_research.reports import build_survival_report, write_report
from research.aegis_research.splits import build_validation_splits
from research.aegis_research.validation import evaluate_validation_splits


def run_experiment(
    config: ResolvedExperimentConfig | ExperimentConfig | dict[str, Any],
) -> dict[str, object]:
    resolved_config = resolve_experiment_config(config)
    config = resolved_config.config
    data = load_market_data(config.data)
    close = _primary_close(close_from_ohlcv(data))
    high = _primary_close(high_from_ohlcv(data))
    low = _primary_close(low_from_ohlcv(data))
    indicators = build_indicators(close, config.indicators)
    labels = build_labels(close, config.labels, high=high, low=low)
    splits = build_validation_splits(
        indicators.index.intersection(labels.dropna().index), config.split
    )
    validation = evaluate_validation_splits(close, indicators, labels, splits, config)
    report = build_survival_report(
        config.name,
        validation.train_metrics,
        validation.test_metrics,
        config.report,
        validation.validation_metadata,
    )

    run_dir = _make_run_dir(config)
    export_model(validation.model, run_dir / "artifacts" / "model.joblib")
    write_report(report, run_dir / "survival_report.json")
    _write_config_artifacts(resolved_config, run_dir)
    _as_frame(validation.probabilities).to_csv(run_dir / "probabilities.csv")
    _as_frame(validation.entries).add_prefix("entry_").join(
        _as_frame(validation.exits).add_prefix("exit_")
    ).to_csv(run_dir / "signals.csv")
    validation.split_metrics.to_csv(run_dir / "split_metrics.csv")

    return {"run_dir": str(run_dir), "report": report}


def _write_config_artifacts(config: ResolvedExperimentConfig, run_dir: Path) -> None:
    (run_dir / "config.yaml").write_text(
        yaml.safe_dump(config.redacted_resolved_config(), sort_keys=False)
    )
    (run_dir / "config_authored.yaml").write_text(
        yaml.safe_dump(config.redacted_authored_config(), sort_keys=False)
    )
    write_report(config.manifest(), run_dir / "config_manifest.json")


def _make_run_dir(config: ExperimentConfig) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(config.output_dir) / f"{timestamp}_{config.name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "artifacts").mkdir()
    return run_dir


def _as_frame(obj):
    return obj.to_frame() if hasattr(obj, "to_frame") else obj
