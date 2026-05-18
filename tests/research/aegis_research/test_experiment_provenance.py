from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from research.aegis_research import data, indicators, labels, models, portfolios, signals, splits
from research.aegis_research import validation as validation_module
from research.aegis_research.config import load_experiment_config, resolve_experiment_config
from research.aegis_research.experiments import run_experiment
from research.aegis_research.provenance import artifacts, experiment_artifacts, manifest
from research.aegis_research.provenance.manifest import ArtifactStatus, RunStatus, validate_manifest
from research.aegis_research.provenance.recorder import RerunMode, RunRecorder
from tests.research.aegis_research.model_plugin_fixtures import make_model_registry


def test_run_experiment_writes_manifest_backed_artifacts(tmp_path: Path) -> None:
    registry = make_model_registry()
    config = load_experiment_config(
        "research/configs/experiments/synthetic_ml_baseline.yaml", model_registry=registry
    )
    config = resolve_experiment_config(
        replace(config.config, output_dir=str(tmp_path)), model_registry=registry
    )

    result = run_experiment(config, run_id="purged-manifest-run")

    run_dir = Path(result["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(manifest, run_dir=run_dir)

    assert result["status"] == RunStatus.COMPLETED
    assert result["report_artifact_id"] == "report.survival"
    assert manifest["run"]["status"] == RunStatus.COMPLETED
    artifact_ids = {artifact["id"] for artifact in manifest["artifacts"]}
    assert "config.resolved" in artifact_ids
    assert "config.authored" in artifact_ids
    assert "data.metadata" in artifact_ids
    assert "data.native" in artifact_ids
    assert "indicators.metadata" in artifact_ids
    assert "indicators.lineage" in artifact_ids
    assert "indicators.diagnostics" in artifact_ids
    assert "indicators.features.schema" in artifact_ids
    assert "indicators.native" in artifact_ids
    assert "indicators.native.metadata" in artifact_ids
    assert "labels.metadata" in artifact_ids
    assert "labels.lineage" in artifact_ids
    assert "labels.diagnostics" in artifact_ids
    assert "labels.evaluation_evidence" in artifact_ids
    assert "labels.target.schema" in artifact_ids
    assert "labels.target" in artifact_ids
    assert "labels.compatibility" in artifact_ids
    assert "labels.native" in artifact_ids
    assert "labels.native.metadata" in artifact_ids
    assert "splits.evidence" in artifact_ids
    assert "report.survival" in artifact_ids
    config_manifest = next(
        artifact for artifact in manifest["artifacts"] if artifact["id"] == "config.manifest"
    )
    assert config_manifest["visibility"] == "private"
    assert "validation.split_0.model" in artifact_ids
    assert "validation.split_0.portfolio.test" in artifact_ids
    assert "validation.split_0.signal_diagnostics.test" in artifact_ids
    assert "validation.split_0.portfolio_diagnostics.test" in artifact_ids
    feature_schema = json.loads((run_dir / "indicators" / "features.schema.json").read_text())
    label_evidence = json.loads((run_dir / "labels" / "evaluation_evidence.json").read_text())
    signal_diagnostics = json.loads(
        (run_dir / "splits" / "split_0" / "signal_diagnostics_test.json").read_text()
    )
    portfolio_diagnostics = json.loads(
        (run_dir / "splits" / "split_0" / "portfolio_diagnostics_test.json").read_text()
    )
    metrics = json.loads((run_dir / "splits" / "split_0" / "metrics_test.json").read_text())
    portfolio_sidecar = json.loads(
        (run_dir / "native" / "portfolios" / "split_0_test.pkl.metadata.json").read_text()
    )
    assert feature_schema["features"]
    assert feature_schema["features"][0]["name"]
    assert label_evidence["metadata"]["evaluation_time"]["kind"] == "fixed_horizon"
    assert signal_diagnostics["policy"]["name"] == "long_only_hysteresis"
    assert signal_diagnostics["cleaned_diagnostics"]["diagnostics_only"] is True
    assert portfolio_diagnostics["execution"]["timing"] == "next_open"
    assert metrics["metric_scope"] == "shared_cash_group"
    assert metrics["metric_assumptions"]["benchmark_status"] == "none"
    assert metrics["metric_evidence"]["sharpe_ratio"]["source"]["identity"] == "sharpe_ratio"
    assert metrics["metric_roles"]["total_return_pct"]["required_gate_input"] is False
    assert portfolio_sidecar["metadata"]["signal_diagnostics"]["set_name"] == "test"
    assert portfolio_sidecar["metadata"]["portfolio_diagnostics"]["execution"]["timing"] == (
        "next_open"
    )
    assert label_evidence["rows"][0]["prediction_times"]["SYN"]
    assert (run_dir / "labels" / "target.csv").exists()
    assert "native_objects" not in json.dumps(feature_schema)
    assert all(artifact["status"] == ArtifactStatus.COMPLETED for artifact in manifest["artifacts"])
    artifact_order = [artifact["id"] for artifact in manifest["artifacts"]]
    assert artifact_order.index("labels.evaluation_evidence") < artifact_order.index(
        "labels.target.schema"
    )
    assert artifact_order.index("indicators.features.schema") < artifact_order.index(
        "splits.evidence"
    )
    assert artifact_order.index("labels.target.schema") < artifact_order.index("splits.evidence")
    assert artifact_order.index("splits.evidence") < artifact_order.index(
        "validation.split_0.model"
    )
    assert artifact_order.index("labels.compatibility") < artifact_order.index(
        "validation.split_0.model"
    )
    assert artifact_order.index("validation.split_0.signals.test") < artifact_order.index(
        "validation.split_0.signal_diagnostics.test"
    )
    assert artifact_order.index(
        "validation.split_0.signal_diagnostics.test"
    ) < artifact_order.index("validation.split_0.portfolio_diagnostics.test")
    assert artifact_order.index(
        "validation.split_0.portfolio_diagnostics.test"
    ) < artifact_order.index("validation.split_0.metrics.test")
    assert not (run_dir / "artifacts" / "model.joblib").exists()


def test_purged_run_writes_per_split_models_and_links_aggregates(tmp_path: Path) -> None:
    registry = make_model_registry()
    config = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml",
        model_registry=registry,
    )
    config = resolve_experiment_config(
        replace(config.config, output_dir=str(tmp_path)), model_registry=registry
    )

    result = run_experiment(config, run_id="purged-run")

    run_dir = Path(result["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(manifest, run_dir=run_dir)
    artifacts = {artifact["id"]: artifact for artifact in manifest["artifacts"]}
    model_ids = [artifact_id for artifact_id in artifacts if artifact_id.endswith(".model")]

    assert len(model_ids) == 5
    assert "model" not in artifacts
    assert artifacts["validation.probabilities"]["upstream_artifact_ids"]
    assert artifacts["validation.signals"]["schema_version"] == (
        "long_only_threshold_state_signals.aggregate.v1"
    )
    assert "validation.signal_diagnostics" in artifacts
    assert artifacts["validation.signal_diagnostics"]["upstream_artifact_ids"] == [
        f"validation.split_{index}.signal_diagnostics.test" for index in range(5)
    ]
    assert artifacts["validation.portfolio_diagnostics"]["schema_version"] == (
        "validation_portfolio_diagnostics.v2"
    )
    assert artifacts["validation.split_0.portfolio_diagnostics.test"]["schema_version"] == (
        "portfolio_diagnostics.v2"
    )
    assert artifacts["validation.split_0.metrics.test"]["schema_version"] == "metrics.v3"
    assert artifacts["validation.split_metrics"]["schema_version"] == "split_metrics.v2"
    assert artifacts["report.survival"]["schema_version"] == "survival_report.v4"
    assert artifacts["validation.portfolio_diagnostics"]["upstream_artifact_ids"] == [
        f"validation.split_{index}.portfolio_diagnostics.test" for index in range(5)
    ]
    assert artifacts["report.survival"]["upstream_artifact_ids"] == [
        "validation.split_metrics",
        *[f"validation.split_{index}.metrics.test" for index in range(5)],
        "splits.evidence",
        "labels.compatibility",
    ]
    assert artifacts["splits.evidence"]["role"] == "split_evidence"
    assert artifacts["splits.evidence"]["upstream_artifact_ids"] == [
        "labels.target.schema",
        "labels.evaluation_evidence",
        "indicators.features.schema",
    ]
    evidence = json.loads((run_dir / "splits" / "evidence.json").read_text())
    aggregate_signal_diagnostics = json.loads((run_dir / "signal_diagnostics.json").read_text())
    aggregate_portfolio_diagnostics = json.loads(
        (run_dir / "portfolio_diagnostics.json").read_text()
    )
    assert evidence["kind"] == "purged_kfold"
    assert evidence["splits"]
    assert "membership" in evidence["splits"][0]["train"]
    assert aggregate_signal_diagnostics["splits"]["split_0"]["test"]["set_name"] == "test"
    assert (
        aggregate_portfolio_diagnostics["splits"]["split_0"]["test"]["execution"]["timing"]
        == "next_open"
    )
    report = json.loads((run_dir / "survival_report.json").read_text())
    split_metrics = (run_dir / "split_metrics.csv").read_text()
    split_metrics_payload = json.loads(
        (run_dir / "splits" / "split_0" / "metrics_test.json").read_text()
    )
    assert report["decision_policy"]["metrics"]["sharpe_ratio"]["policy"] == "all_splits_pass"
    assert report["metric_roles"]["gate_evidence"] == "per_split_test_metrics"
    assert report["gate_outcomes"]
    metric_gate = next(gate for gate in report["gate_outcomes"] if gate["metric"] is not None)
    assert {
        "name",
        "metric",
        "source_scope",
        "split",
        "actual_value",
        "availability",
        "threshold",
        "comparator",
        "status",
        "reason",
        "required",
    } <= set(metric_gate)
    assert metric_gate["evidence"]["source"]["identity"]
    assert "warnings" in metric_gate["evidence"]
    assert report["metric_evidence_summary"]["metrics"]["sharpe_ratio"]["splits"]
    assert split_metrics_payload["metric_evidence"]["sharpe_ratio"]
    assert "metric_evidence" not in split_metrics.splitlines()[0]


def test_failed_split_run_preserves_prior_completed_split_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = make_model_registry()
    config = load_experiment_config(
        "research/configs/experiments/synthetic_purged_fixlb_baseline.yaml",
        model_registry=registry,
    )
    config = resolve_experiment_config(
        replace(config.config, output_dir=str(tmp_path)), model_registry=registry
    )
    original_train_model = validation_module.train_model
    call_count = 0

    def fail_on_third_split(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise RuntimeError("split 3 failed")
        return original_train_model(*args, **kwargs)

    monkeypatch.setattr(validation_module, "train_model", fail_on_third_split)

    with pytest.raises(RuntimeError, match="split 3 failed"):
        run_experiment(config, run_id="purged-failed-run")

    run_dir = tmp_path / "purged-failed-run"
    payload = json.loads((run_dir / "manifest.json").read_text())
    validate_manifest(payload, run_dir=run_dir)
    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}

    assert payload["run"]["status"] == RunStatus.FAILED
    assert artifacts["validation.split_0.model"]["status"] == ArtifactStatus.COMPLETED
    assert artifacts["validation.split_1.model"]["status"] == ArtifactStatus.COMPLETED
    assert "validation.split_2.model" not in artifacts


def test_csv_artifact_write_failure_marks_failed_without_partial_file(tmp_path: Path) -> None:
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run",
        run_id="run",
        run_label="artifact-failure",
        mode=RerunMode.NEW,
        config={"schema_version": 1},
    )

    with pytest.raises(OSError, match="csv failed"):
        experiment_artifacts._write_csv_artifact(
            recorder,
            artifact_id="validation.metrics",
            role="metrics",
            producer_stage="validation",
            path="metrics.csv",
            frame=_FailingCsvFrame(),
            schema_version="metrics.v1",
        )

    payload = json.loads(recorder.manifest_path.read_text())
    artifact = payload["artifacts"][0]

    assert artifact["status"] == ArtifactStatus.FAILED
    assert artifact["diagnostic"]["message"] == "csv failed"
    assert not (recorder.run_dir / "metrics.csv").exists()
    assert not list(recorder.run_dir.glob(".metrics.csv.*.tmp"))
    validate_manifest(payload, run_dir=recorder.run_dir)


def test_json_artifact_write_failure_marks_failed_without_partial_file(tmp_path: Path) -> None:
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run",
        run_id="run",
        run_label="artifact-failure",
        mode=RerunMode.NEW,
        config={"schema_version": 1},
    )

    with pytest.raises(TypeError):
        experiment_artifacts._write_json_artifact(
            recorder,
            artifact_id="validation.split_0.signal_diagnostics.test",
            role="signal_diagnostics",
            producer_stage="validation",
            path="splits/split_0/signal_diagnostics_test.json",
            payload={"bad": object()},
            schema_version="signal_diagnostics.v1",
        )

    payload = json.loads(recorder.manifest_path.read_text())
    artifact = payload["artifacts"][0]

    assert artifact["status"] == ArtifactStatus.FAILED
    assert not (recorder.run_dir / "splits" / "split_0" / "signal_diagnostics_test.json").exists()
    assert not list(
        (recorder.run_dir / "splits" / "split_0").glob(".signal_diagnostics_test.json.*.tmp")
    )
    validate_manifest(payload, run_dir=recorder.run_dir)


def test_text_artifact_completion_failure_removes_uncompleted_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run",
        run_id="run",
        run_label="artifact-failure",
        mode=RerunMode.NEW,
        config={"schema_version": 1},
    )

    def fail_complete(*_args, **_kwargs):
        raise OSError("manifest persist failed")

    monkeypatch.setattr(recorder.artifacts, "complete_existing_file", fail_complete)

    with pytest.raises(OSError, match="manifest persist failed"):
        experiment_artifacts._write_text_artifact(
            recorder,
            artifact_id="config.resolved",
            role="resolved_config",
            producer_stage="config",
            path="config.yaml",
            text="name: test\n",
            schema_version="resolved_config.v1",
        )

    payload = json.loads(recorder.manifest_path.read_text())
    artifact = payload["artifacts"][0]

    assert artifact["status"] == ArtifactStatus.FAILED
    assert artifact["diagnostic"]["message"] == "manifest persist failed"
    assert not (recorder.run_dir / "config.yaml").exists()
    validate_manifest(payload, run_dir=recorder.run_dir)


def test_architecture_boundaries_remain_one_way() -> None:
    stage_modules = [data, indicators, labels, splits, models, signals, portfolios]

    for module in stage_modules:
        source = inspect.getsource(module)
        assert "provenance.recorder" not in source
        assert "RunRecorder" not in source

    for module in [manifest, artifacts]:
        source = inspect.getsource(module)
        assert "aegis_research.validation" not in source
        assert "aegis_research.portfolios" not in source
        assert "aegis_research.labels" not in source


class _FailingCsvFrame:
    columns: ClassVar[list[str]] = ["value"]

    def __len__(self) -> int:
        return 1

    def to_csv(self, path: str | Path) -> None:
        Path(path).write_text("partial")
        raise OSError("csv failed")
