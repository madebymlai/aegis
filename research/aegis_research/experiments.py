from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from research.aegis_research.config import (
    ExperimentConfig,
    ResolvedExperimentConfig,
    redact_text,
    resolve_experiment_config,
)
from research.aegis_research.data import (
    load_market_data_result,
    required_ohlcv_features,
)
from research.aegis_research.indicators import build_indicator_result, build_model_feature_matrix
from research.aegis_research.labels import build_label_result
from research.aegis_research.provenance.evidence import (
    apply_seed_policy,
    capture_run_start_evidence,
)
from research.aegis_research.provenance.experiment_artifacts import ExperimentArtifactWriter
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.reports import build_survival_report
from research.aegis_research.splits import build_validation_splits_result
from research.aegis_research.validation import evaluate_validation_splits


def run_experiment(
    config: ResolvedExperimentConfig | ExperimentConfig | dict[str, Any],
    *,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
) -> dict[str, object]:
    resolved_config = resolve_experiment_config(config)
    config = resolved_config.config
    known_secrets = _known_config_secret_values(resolved_config.authored_config)
    run_start_evidence = capture_run_start_evidence(resolved_config, repo_path=Path.cwd())
    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=run_start_evidence["config"],
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    recorder.manifest.evidence = {
        key: value for key, value in run_start_evidence.items() if key != "config"
    }
    recorder.manifest.evidence["seed_policy"] |= apply_seed_policy(config.data.seed)
    recorder.persist()
    try:
        artifacts = ExperimentArtifactWriter(recorder)
        artifacts.write_config_artifacts(resolved_config)

        required_features = required_ohlcv_features(config.labels)
        data_result = load_market_data_result(
            config.data,
            required_features=required_features,
        )
        artifacts.write_data_metadata_artifact(data_result)
        data_result.assert_usable()
        artifacts.write_data_native_artifact(data_result)
        close = data_result.feature("Close")
        high = data_result.feature("High") if "High" in required_features else None
        low = data_result.feature("Low") if "Low" in required_features else None
        indicator_result = build_indicator_result(close, config.indicators)
        label_result = build_label_result(close, config.labels, high=high, low=low)
        labels = label_result.labels
        model_features = build_model_feature_matrix(
            indicator_result,
            labels,
            invalid_value_policy=config.indicators.invalid_value_policy,
        )
        indicators = model_features.frame
        splits_result = build_validation_splits_result(
            model_features.eligible_index,
            config.split,
        )
        artifacts.write_indicator_artifacts(indicator_result, model_features)
        artifacts.write_stage_native_artifacts(label_result, splits_result)
        split_metric_ids: list[str] = []

        def record_split_artifacts(split_result) -> None:
            split_metric_ids.extend(artifacts.write_split_artifacts(split_result))

        validation = evaluate_validation_splits(
            close,
            indicators,
            labels,
            splits_result.splits,
            config,
            on_split_result=record_split_artifacts,
        )
        report = build_survival_report(
            config.name,
            validation.train_metrics,
            validation.test_metrics,
            config.report,
            validation.validation_metadata,
        )

        artifacts.write_validation_aggregates(validation, split_metric_ids=split_metric_ids)
        artifacts.write_report_artifact(report)
        recorder.mark_run_completed()

        return {
            "run_id": recorder.manifest.run_id,
            "run_dir": str(recorder.run_dir),
            "manifest_path": str(recorder.manifest_path),
            "status": recorder.manifest.status,
            "started_at": recorder.manifest.started_at,
            "finished_at": recorder.manifest.finished_at,
            "report_artifact_id": "report.survival",
            "report": report,
        }
    except KeyboardInterrupt:
        recorder.mark_run_interrupted()
        raise
    except Exception as error:
        recorder.mark_run_failed(diagnostic=_redacted_diagnostic(error, known_secrets))
        raise


def _redacted_diagnostic(error: Exception, known_secrets: tuple[str, ...]) -> dict[str, str]:
    message = _redact_nonportable_paths(redact_text(str(error), known_secrets))
    return {
        "error_type": type(error).__name__,
        "message": message[:1000],
    }


def _redact_nonportable_paths(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    return re.sub(r"(?<!\w)/(?:[^\s'\"]+/)*[^\s'\"]+", "<path>", value)


def _known_config_secret_values(value: Any) -> tuple[str, ...]:
    secrets: list[str] = []
    _collect_config_secret_values(value, secrets)
    return tuple(secrets)


def _collect_config_secret_values(value: Any, secrets: list[str]) -> None:
    if isinstance(value, dict) and set(value) == {"env"}:
        secret = os.environ.get(str(value["env"]), "")
        if secret:
            secrets.append(secret)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_config_secret_values(item, secrets)
        return
    if isinstance(value, list):
        for item in value:
            _collect_config_secret_values(item, secrets)
