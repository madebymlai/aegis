from __future__ import annotations

from typing import Any

import pandas as pd
import yaml

from research.aegis_research.config import ResolvedExperimentConfig
from research.aegis_research.data import MarketDataResult, assert_public_metadata_safe
from research.aegis_research.data_schema import table_shape
from research.aegis_research.indicators import IndicatorResult, ModelFeatureMatrix
from research.aegis_research.labels import LabelResult
from research.aegis_research.models import export_model
from research.aegis_research.provenance.manifest import ArtifactVisibility, atomic_write_json
from research.aegis_research.provenance.native import NativeArtifactWriter
from research.aegis_research.provenance.recorder import RunRecorder
from research.aegis_research.splits import ValidationSplitsResult
from research.aegis_research.validation import SplitValidationResult, ValidationResult


class ExperimentArtifactWriter:
    def __init__(self, recorder: RunRecorder) -> None:
        self.recorder = recorder
        self.native_writer = NativeArtifactWriter(
            recorder.manifest,
            recorder.run_dir,
            persist=recorder.persist,
        )

    def write_config_artifacts(self, config: ResolvedExperimentConfig) -> None:
        _write_text_artifact(
            self.recorder,
            artifact_id="config.resolved",
            role="resolved_config",
            producer_stage="config",
            path="config.yaml",
            text=yaml.safe_dump(config.redacted_resolved_config(), sort_keys=False),
            schema_version="resolved_config.v1",
        )
        _write_text_artifact(
            self.recorder,
            artifact_id="config.authored",
            role="authored_config",
            producer_stage="config",
            path="config_authored.yaml",
            text=yaml.safe_dump(config.redacted_authored_config(), sort_keys=False),
            schema_version="authored_config.v1",
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="config.manifest",
            role="config_manifest",
            producer_stage="config",
            path="config_manifest.json",
            payload=config.manifest(),
            schema_version="config_manifest.v1",
            visibility=ArtifactVisibility.PRIVATE,
        )

    def write_data_metadata_artifact(self, data_result: MarketDataResult) -> None:
        assert_public_metadata_safe(
            data_result.metadata,
            known_secrets=data_result.known_secrets,
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="data.metadata",
            role="data_metadata",
            producer_stage="data",
            path="data_metadata.json",
            payload=data_result.metadata,
            schema_version="data_metadata.v1",
        )

    def write_data_native_artifact(self, data_result: MarketDataResult) -> None:
        self.native_writer.write_native_artifact(
            artifact_id="data.native",
            role="data_native",
            producer_stage="data",
            path="native/data.pkl",
            obj=data_result.native_data,
            metadata=data_result.metadata,
            known_secrets=data_result.known_secrets,
        )

    def write_indicator_artifacts(
        self,
        indicator_result: IndicatorResult,
        model_features: ModelFeatureMatrix,
    ) -> None:
        metadata = indicator_result.metadata
        lineage = {"lineage": indicator_result.lineage}
        diagnostics = {
            "indicator_stage": indicator_result.diagnostics,
            "model_boundary": model_features.diagnostics,
        }
        feature_schema = {
            "metadata": model_features.metadata,
            "features": [
                {"name": feature_name, **mapping}
                for feature_name, mapping in model_features.feature_mapping.items()
            ],
        }
        for payload in (metadata, lineage, diagnostics, feature_schema):
            assert_public_metadata_safe(payload)

        _write_json_artifact(
            self.recorder,
            artifact_id="indicators.metadata",
            role="indicator_metadata",
            producer_stage="indicators",
            path="indicators/metadata.json",
            payload=metadata,
            schema_version="indicators_metadata.v1",
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="indicators.lineage",
            role="indicator_lineage",
            producer_stage="indicators",
            path="indicators/lineage.json",
            payload=lineage,
            schema_version="indicator_lineage.v1",
            upstream_artifact_ids=["indicators.metadata"],
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="indicators.diagnostics",
            role="indicator_diagnostics",
            producer_stage="indicators",
            path="indicators/diagnostics.json",
            payload=diagnostics,
            schema_version="indicator_diagnostics.v1",
            upstream_artifact_ids=["indicators.metadata"],
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="indicators.features.schema",
            role="model_feature_schema",
            producer_stage="indicators",
            path="indicators/features.schema.json",
            payload=feature_schema,
            schema_version="model_feature_schema.v1",
            upstream_artifact_ids=["indicators.lineage", "indicators.diagnostics"],
        )
        if indicator_result.native_objects:
            native_metadata = {
                "native_object_ids": sorted(indicator_result.native_objects),
                "native_output_shapes": {
                    indicator_id: {
                        output_name: table_shape(output) for output_name, output in outputs.items()
                    }
                    for indicator_id, outputs in indicator_result.native_outputs.items()
                },
            }
            self.native_writer.write_native_artifact(
                artifact_id="indicators.native",
                role="indicators_native",
                producer_stage="indicators",
                path="native/indicators.pkl",
                obj=indicator_result.native_objects,
                metadata=native_metadata,
            )

    def write_label_artifacts(self, label_result: LabelResult) -> None:
        lineage = {"lineage": label_result.lineage}
        diagnostics = label_result.diagnostics
        target_schema = label_result.target_schema
        payloads = (label_result.metadata, lineage, diagnostics, target_schema)
        for payload in payloads:
            assert_public_metadata_safe(payload)

        _write_json_artifact(
            self.recorder,
            artifact_id="labels.metadata",
            role="label_metadata",
            producer_stage="labels",
            path="labels/metadata.json",
            payload=label_result.metadata,
            schema_version="labels_metadata.v1",
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="labels.lineage",
            role="label_lineage",
            producer_stage="labels",
            path="labels/lineage.json",
            payload=lineage,
            schema_version="label_lineage.v1",
            upstream_artifact_ids=["labels.metadata"],
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="labels.diagnostics",
            role="label_diagnostics",
            producer_stage="labels",
            path="labels/diagnostics.json",
            payload=diagnostics,
            schema_version="label_diagnostics.v1",
            upstream_artifact_ids=["labels.metadata"],
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="labels.target.schema",
            role="label_target_schema",
            producer_stage="labels",
            path="labels/target.schema.json",
            payload=target_schema,
            schema_version="label_target_schema.v1",
            upstream_artifact_ids=["labels.lineage", "labels.diagnostics"],
        )
        _write_csv_artifact(
            self.recorder,
            artifact_id="labels.target",
            role="label_target_panel",
            producer_stage="labels",
            path="labels/target.csv",
            frame=label_result.labels,
            schema_version="label_target_panel.v1",
            upstream_artifact_ids=["labels.target.schema"],
        )
        if label_result.native_object is not None:
            native_metadata = {
                "kind": label_result.metadata["kind"],
                "native_output_shape": label_result.metadata["native_output_shape"],
                "target": label_result.metadata["target"],
            }
            self.native_writer.write_native_artifact(
                artifact_id="labels.native",
                role="labels_native",
                producer_stage="labels",
                path="native/labels.pkl",
                obj=label_result.native_object,
                metadata=native_metadata,
            )

    def write_label_compatibility_artifact(self, compatibility: dict[str, Any]) -> None:
        assert_public_metadata_safe(compatibility)
        _write_json_artifact(
            self.recorder,
            artifact_id="labels.compatibility",
            role="label_compatibility",
            producer_stage="labels",
            path="labels/compatibility.json",
            payload=compatibility,
            schema_version="label_compatibility.v1",
            upstream_artifact_ids=["labels.target.schema"],
        )

    def write_split_native_artifact(self, splits_result: ValidationSplitsResult) -> None:
        if splits_result.native_object is not None:
            self.native_writer.write_native_artifact(
                artifact_id="splits.native",
                role="splits_native",
                producer_stage="splits",
                path="native/splitter.pkl",
                obj=splits_result.native_object,
                metadata=splits_result.metadata,
            )

    def write_split_artifacts(self, split: SplitValidationResult) -> list[str]:
        metric_ids: list[str] = []
        prefix = f"validation.{split.label}"
        directory = f"splits/{split.label}"
        _write_model_artifact(
            self.recorder,
            artifact_id=f"{prefix}.model",
            producer_stage="validation",
            path=f"{directory}/model.joblib",
            model=split.model,
        )
        for set_name in ("train", "test"):
            probabilities = getattr(split, f"{set_name}_probabilities")
            entries = getattr(split, f"{set_name}_entries")
            exits = getattr(split, f"{set_name}_exits")
            metrics = getattr(split, f"{set_name}_metrics")
            _write_csv_artifact(
                self.recorder,
                artifact_id=f"{prefix}.probabilities.{set_name}",
                role="probabilities",
                producer_stage="validation",
                path=f"{directory}/probabilities_{set_name}.csv",
                frame=probabilities,
                schema_version="probabilities.v1",
                upstream_artifact_ids=[f"{prefix}.model"],
            )
            _write_csv_artifact(
                self.recorder,
                artifact_id=f"{prefix}.signals.{set_name}",
                role="signals",
                producer_stage="validation",
                path=f"{directory}/signals_{set_name}.csv",
                frame=_signals_frame(entries, exits),
                schema_version="signals.v1",
                upstream_artifact_ids=[f"{prefix}.probabilities.{set_name}"],
            )
            metric_id = f"{prefix}.metrics.{set_name}"
            _write_json_artifact(
                self.recorder,
                artifact_id=metric_id,
                role="metrics",
                producer_stage="validation",
                path=f"{directory}/metrics_{set_name}.json",
                payload=metrics,
                schema_version="metrics.v1",
                upstream_artifact_ids=[f"{prefix}.signals.{set_name}"],
            )
            metric_ids.append(metric_id)
            self.native_writer.write_native_artifact(
                artifact_id=f"{prefix}.portfolio.{set_name}",
                role="portfolio",
                producer_stage="validation",
                path=f"native/portfolios/{split.label}_{set_name}.pkl",
                obj=getattr(split, f"{set_name}_portfolio"),
                metadata={"split": split.label, "set": set_name, **split.metadata},
            )
        return metric_ids

    def write_validation_aggregates(
        self,
        validation: ValidationResult,
        *,
        split_metric_ids: list[str],
    ) -> None:
        probability_ids = [
            f"validation.{split.label}.probabilities.test" for split in validation.split_results
        ]
        signal_ids = [
            f"validation.{split.label}.signals.test" for split in validation.split_results
        ]
        _write_csv_artifact(
            self.recorder,
            artifact_id="validation.probabilities",
            role="aggregate_probabilities",
            producer_stage="validation",
            path="probabilities.csv",
            frame=validation.probabilities,
            schema_version="probabilities.aggregate.v1",
            upstream_artifact_ids=probability_ids,
        )
        _write_csv_artifact(
            self.recorder,
            artifact_id="validation.signals",
            role="aggregate_signals",
            producer_stage="validation",
            path="signals.csv",
            frame=_signals_frame(validation.entries, validation.exits),
            schema_version="signals.aggregate.v1",
            upstream_artifact_ids=signal_ids,
        )
        _write_csv_artifact(
            self.recorder,
            artifact_id="validation.split_metrics",
            role="split_metrics",
            producer_stage="validation",
            path="split_metrics.csv",
            frame=validation.split_metrics,
            schema_version="split_metrics.v1",
            upstream_artifact_ids=split_metric_ids,
        )

    def write_report_artifact(self, report: dict[str, Any]) -> None:
        _write_json_artifact(
            self.recorder,
            artifact_id="report.survival",
            role="survival_report",
            producer_stage="report",
            path="survival_report.json",
            payload=report,
            schema_version="survival_report.v1",
            upstream_artifact_ids=["validation.split_metrics"],
        )


def _write_json_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    payload: dict[str, Any],
    schema_version: str,
    upstream_artifact_ids: list[str] | None = None,
    visibility: str = ArtifactVisibility.PUBLIC,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="json",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
        upstream_artifact_ids=upstream_artifact_ids,
        visibility=visibility,
    )
    recorder.artifacts.begin_artifact_write(artifact_id)
    atomic_write_json(recorder.run_dir / path, payload)
    recorder.artifacts.complete_existing_file(artifact_id)


def _write_text_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    text: str,
    schema_version: str,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="yaml",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
    )
    recorder.artifacts.begin_artifact_write(artifact_id)
    target = recorder.run_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    recorder.artifacts.complete_existing_file(artifact_id)


def _write_csv_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    role: str,
    producer_stage: str,
    path: str,
    frame,
    schema_version: str,
    upstream_artifact_ids: list[str] | None = None,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="csv",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
        upstream_artifact_ids=upstream_artifact_ids,
    )
    recorder.artifacts.begin_artifact_write(artifact_id)
    target = recorder.run_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target)
    recorder.artifacts.complete_existing_file(
        artifact_id,
        shape={"rows": len(frame), "columns": len(frame.columns)},
    )


def _write_model_artifact(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    producer_stage: str,
    path: str,
    model,
) -> None:
    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role="model",
        artifact_type="joblib",
        producer_stage=producer_stage,
        path=path,
        schema_version="model.joblib.v1",
    )
    recorder.artifacts.begin_artifact_write(artifact_id)
    export_model(model, recorder.run_dir / path)
    recorder.artifacts.complete_existing_file(artifact_id)


def _signals_frame(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    return pd.concat({"entry": entries, "exit": exits}, axis=1)
