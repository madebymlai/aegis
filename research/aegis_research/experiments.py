from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from research.aegis_research.component_registry import ComponentSelection, FrozenComponentRegistry
from research.aegis_research.config import (
    ConfigValidationError,
    ConfigValidationIssue,
    ResolvedLaneConfig,
    TrainLaneConfig,
    known_config_secret_values,
    redact_text,
    resolve_lane_config,
)
from research.aegis_research.data import (
    load_market_data_result,
    market_data_bundle,
    required_experiment_ohlcv_features,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
    build_data_array_contract,
    merge_data_arrays,
    with_data_array_contract_metadata,
)
from research.aegis_research.indicators import build_model_feature_matrix
from research.aegis_research.model_registry import FrozenModelRegistry, ModelRegistry
from research.aegis_research.models import (
    assert_target_model_compatible,
    target_model_compatibility,
)
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
    config: ResolvedLaneConfig | TrainLaneConfig | dict[str, Any],
    *,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
    label_result_builder: Callable[..., Any] | None = None,
    indicator_result_builder: Callable[..., Any] | None = None,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
    on_run_started: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, object]:
    resolved_config = resolve_lane_config(
        config,
        model_registry=model_registry,
        expected_lane="train",
    )
    if resolved_config.model_registry is None:
        raise ConfigValidationError(
            [
                ConfigValidationIssue(
                    "train.model.id", "registered model plugin registry is required"
                )
            ]
        )
    config = resolved_config.config
    array_contract = _train_data_array_contract(config, resolved_config.component_registry)
    known_secrets = known_config_secret_values(resolved_config.authored_config)
    run_start_evidence = capture_run_start_evidence(resolved_config, repo_path=Path.cwd())
    run_start_evidence["data_arrays"] = array_contract.metadata()
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
    try:
        recorder.persist()
        if on_run_started is not None:
            on_run_started(_run_refs(recorder))
        artifacts = ExperimentArtifactWriter(recorder)
        artifacts.write_config_artifacts(resolved_config)

        array_contract.assert_configured()
        required_features = array_contract.required_arrays
        data_result = load_market_data_result(
            config.data,
            required_features=required_features,
        )
        data_result = with_data_array_contract_metadata(data_result, array_contract)
        artifacts.write_data_metadata_artifact(data_result)
        data_result.assert_usable()
        artifacts.write_data_native_artifact(data_result)
        data_bundle = market_data_bundle(data_result)
        close_prices = data_bundle.feature("Close")
        execution_open_prices = (
            data_bundle.feature("Open") if "Open" in array_contract.pipeline_required_arrays else None
        )
        if label_result_builder is None:
            _raise_missing_label_result_builder()
        label_result = label_result_builder(data_bundle)
        artifacts.write_label_artifacts(
            label_result,
            max_public_artifact_bytes=config.split.max_public_artifact_bytes,
        )
        labels = label_result.labels
        pre_split_compatibility = target_model_compatibility(
            labels,
            config.model,
            label_result.target_schema,
            phase="pre_split",
            model_registry=resolved_config.model_registry,
        )
        if not pre_split_compatibility["compatible"]:
            artifacts.write_label_compatibility_artifact(pre_split_compatibility)
            assert_target_model_compatible(pre_split_compatibility)

        if indicator_result_builder is None:
            _raise_missing_indicator_result_builder()
        indicator_result = indicator_result_builder(data_bundle)
        try:
            model_features = build_model_feature_matrix(
                indicator_result,
                labels,
            )
        except Exception as error:
            artifacts.write_label_compatibility_artifact(
                _pre_split_compatibility_failure(label_result.target_schema, error)
            )
            raise
        indicators = model_features.frame
        artifacts.write_indicator_artifacts(indicator_result, model_features)
        splits_result = build_validation_splits_result(
            model_features.eligible_index,
            config.split,
            target_metadata=_split_target_metadata(label_result),
            evaluation_evidence=label_result.evaluation_evidence,
        )
        artifacts.write_split_evidence_artifacts(splits_result)
        compatibility = target_model_compatibility(
            labels,
            config.model,
            label_result.target_schema,
            splits_result.splits,
            phase="post_split",
            split_metadata=splits_result.metadata,
            model_registry=resolved_config.model_registry,
        )
        artifacts.write_label_compatibility_artifact(compatibility)
        assert_target_model_compatible(compatibility)
        artifacts.write_split_native_artifact(splits_result)
        split_metric_ids: list[str] = []

        def record_split_artifacts(split_result) -> None:
            split_metric_ids.extend(artifacts.write_split_artifacts(split_result))

        validation = evaluate_validation_splits(
            close_prices,
            indicators,
            labels,
            splits_result.splits,
            config,
            open_prices=execution_open_prices,
            target_schema=label_result.target_schema,
            split_metadata=splits_result.metadata,
            compatibility=compatibility,
            model_registry=resolved_config.model_registry,
            on_split_result=record_split_artifacts,
        )
        report = build_survival_report(
            config.name,
            validation.train_metrics,
            validation.test_metrics,
            config.report,
            split_metric_evidence=validation.split_metric_evidence,
            validation_metadata=validation.validation_metadata,
        )

        artifacts.write_validation_aggregates(validation, split_metric_ids=split_metric_ids)
        artifacts.write_report_artifact(report, split_metric_ids=split_metric_ids)
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


def _run_refs(recorder) -> dict[str, Any]:
    return {
        "run_id": recorder.manifest.run_id,
        "run_dir": str(recorder.run_dir),
        "manifest_path": str(recorder.manifest_path),
        "status": recorder.manifest.status,
        "started_at": recorder.manifest.started_at,
        "finished_at": recorder.manifest.finished_at,
    }


def _train_data_array_contract(
    config: TrainLaneConfig,
    component_registry: FrozenComponentRegistry | None,
) -> DataArrayContract:
    return build_data_array_contract(
        configured_arrays=config.data.effective_arrays,
        component_required_arrays=_train_component_required_arrays(config, component_registry),
        pipeline_required_arrays=required_experiment_ohlcv_features(None, config.signals),
    )


def _train_component_required_arrays(
    config: TrainLaneConfig,
    component_registry: FrozenComponentRegistry | None,
) -> tuple[str, ...]:
    if component_registry is None:
        return ()
    required: list[tuple[str, ...]] = []
    if config.label.source == "component":
        required.append(
            component_registry.get(ComponentSelection("labels", config.label.id)).input_names
        )
    for ref in config.indicators:
        if ref.source != "component":
            continue
        for component_id in ref.expanded_ids(component_registry.ids("indicators")):
            required.append(
                component_registry.get(ComponentSelection("indicators", component_id)).input_names
            )
    return merge_data_arrays(*required)


def _redacted_diagnostic(error: Exception, known_secrets: tuple[str, ...]) -> dict[str, str]:
    message = _redact_nonportable_paths(redact_text(str(error), known_secrets))
    return {
        "error_type": type(error).__name__,
        "message": message[:1000],
    }


def _split_target_metadata(label_result) -> dict[str, object]:
    target_schema = label_result.target_schema
    return {
        "target_kind": target_schema.get("target_kind"),
        "target_role": target_schema.get("target_role"),
        "split_safety": label_result.split_safety,
        "schema_artifact_id": "labels.target.schema",
    }


def _pre_split_compatibility_failure(
    target_schema: dict[str, object],
    error: Exception,
) -> dict[str, object]:
    return {
        "phase": "pre_split",
        "compatible": False,
        "target_kind": target_schema.get("target_kind"),
        "target_role": target_schema.get("target_role"),
        "model_plugin_id": None,
        "split_safety": target_schema.get("split_safety", {}),
        "splits": [],
        "failure_reason": str(error),
    }


def _raise_missing_label_result_builder() -> None:
    raise ConfigValidationError(
        [
            ConfigValidationIssue(
                "train.label",
                "component label source refs are required; use aerd run --train or pass a label_result_builder",
            )
        ]
    )


def _raise_missing_indicator_result_builder() -> None:
    raise ConfigValidationError(
        [
            ConfigValidationIssue(
                "indicators",
                "component indicator source refs are required; use aerd run --train or pass an indicator_result_builder",
            )
        ]
    )


def _redact_nonportable_paths(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    return re.sub(r"(?<!\w)/(?:[^\s'\"]+/)*[^\s'\"]+", "<path>", value)
