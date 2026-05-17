from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from research.aegis_research.config import ResolvedExperimentConfig
from research.aegis_research.data import MarketDataResult, assert_public_metadata_safe
from research.aegis_research.data_schema import index_identity, table_shape
from research.aegis_research.indicators import IndicatorResult, ModelFeatureMatrix
from research.aegis_research.labels import LabelResult
from research.aegis_research.provenance.manifest import (
    ArtifactVisibility,
    atomic_write_json,
    canonical_json_bytes,
)
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

    def write_label_artifacts(
        self,
        label_result: LabelResult,
        *,
        max_public_artifact_bytes: int | None = None,
    ) -> None:
        lineage = {"lineage": label_result.lineage}
        diagnostics = label_result.diagnostics
        target_schema = label_result.target_schema
        evaluation_evidence = _label_evaluation_evidence_payload(
            label_result,
            max_public_artifact_bytes=max_public_artifact_bytes,
        )
        payloads = (label_result.metadata, lineage, diagnostics, evaluation_evidence, target_schema)
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
            artifact_id="labels.evaluation_evidence",
            role="label_evaluation_evidence",
            producer_stage="labels",
            path="labels/evaluation_evidence.json",
            payload=evaluation_evidence,
            schema_version="label_evaluation_evidence.v1",
            upstream_artifact_ids=["labels.metadata", "labels.lineage"],
        )
        _write_json_artifact(
            self.recorder,
            artifact_id="labels.target.schema",
            role="label_target_schema",
            producer_stage="labels",
            path="labels/target.schema.json",
            payload=target_schema,
            schema_version="label_target_schema.v1",
            upstream_artifact_ids=[
                "labels.lineage",
                "labels.diagnostics",
                "labels.evaluation_evidence",
            ],
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

    def write_split_evidence_artifacts(self, splits_result: ValidationSplitsResult) -> None:
        evidence = _split_evidence_payload(splits_result.metadata)
        assert_public_metadata_safe(evidence)
        _write_json_artifact(
            self.recorder,
            artifact_id="splits.evidence",
            role="split_evidence",
            producer_stage="splits",
            path="splits/evidence.json",
            payload=evidence,
            schema_version="split_evidence.v1",
            upstream_artifact_ids=[
                "labels.target.schema",
                "labels.evaluation_evidence",
                "indicators.features.schema",
            ],
        )

    def write_split_artifacts(self, split: SplitValidationResult) -> list[str]:
        metric_ids: list[str] = []
        prefix = f"validation.{split.label}"
        directory = f"splits/{split.label}"
        assert_public_metadata_safe(split.model.metadata)
        self.native_writer.write_native_artifact(
            artifact_id=f"{prefix}.model",
            role="validation_model_state",
            producer_stage="validation",
            path=f"{directory}/model.joblib",
            obj=split.model.state,
            schema_version=split.model.metadata["trusted_loading"]["state_schema_version"],
            metadata=split.model.metadata,
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
                schema_version="positive_class_probabilities.v1",
                upstream_artifact_ids=[f"{prefix}.model.metadata"],
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
            schema_version="survival_report.v2",
            upstream_artifact_ids=[
                "validation.split_metrics",
                "splits.evidence",
                "labels.compatibility",
            ],
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
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: atomic_write_json(target, payload),
    )


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
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: _atomic_write_text(target, text),
    )


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
    _write_artifact_file(
        recorder,
        artifact_id=artifact_id,
        path=path,
        write=lambda target: _atomic_write_csv(target, frame),
        shape=lambda: {"rows": len(frame), "columns": len(frame.columns)},
    )


def _write_artifact_file(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    path: str,
    write: Callable[[Path], None],
    shape: Callable[[], dict[str, Any]] | None = None,
) -> None:
    target = recorder.run_dir / path
    recorder.artifacts.begin_artifact_write(artifact_id)
    try:
        write(target)
        recorder.artifacts.complete_existing_file(
            artifact_id,
            shape=shape() if shape is not None else None,
        )
    except Exception as error:
        try:
            _fail_artifact_write(recorder, artifact_id=artifact_id, target=target, error=error)
        except Exception as failure_error:
            error.add_note(
                f"failed to mark artifact {artifact_id!r} as failed: {failure_error}"
            )
        raise


def _fail_artifact_write(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    target: Path,
    error: Exception,
) -> None:
    if target.exists():
        target.unlink()
    recorder.artifacts.fail_artifact(
        artifact_id,
        {"error_type": type(error).__name__, "message": str(error)[:1000]},
    )


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode())


def _atomic_write_csv(path: Path, frame: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(target)
    try:
        frame.to_csv(temp_path)
        _fsync_file(temp_path)
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(target)
    try:
        with temp_path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(target)
        _fsync_parent(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _temp_path(target: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        temp_path.chmod(0o600)
    return temp_path


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _label_evaluation_evidence_payload(
    label_result: LabelResult,
    *,
    max_public_artifact_bytes: int | None = None,
) -> dict[str, Any]:
    evidence = label_result.evaluation_evidence
    payload = {
        "metadata": evidence.metadata,
        "index": index_identity(label_result.labels.index),
        "columns": [str(column) for column in label_result.labels.columns],
        "rows": [
            {
                "position": position,
                "timestamp": _public_time_value(index_value),
                "prediction_times": _time_row(evidence.prediction_times.iloc[position]),
                "evaluation_times": _time_row(evidence.evaluation_times.iloc[position]),
            }
            for position, index_value in enumerate(label_result.labels.index)
        ],
    }
    return _public_json_artifact_payload(
        payload,
        max_public_artifact_bytes=max_public_artifact_bytes,
        artifact_name="label evaluation evidence",
    )


def _public_json_artifact_payload(
    payload: dict[str, Any],
    *,
    max_public_artifact_bytes: int | None,
    artifact_name: str,
) -> dict[str, Any]:
    if max_public_artifact_bytes is None:
        return payload

    return _apply_public_artifact_byte_cap(
        {
            **payload,
            "resource_estimate": {"max_public_artifact_bytes": max_public_artifact_bytes},
        },
        max_public_artifact_bytes=max_public_artifact_bytes,
        artifact_name=artifact_name,
    )


def _split_evidence_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    resource_estimate = metadata.get("resource_estimate")
    if not isinstance(resource_estimate, dict):
        return metadata

    payload = {**metadata, "resource_estimate": dict(resource_estimate)}
    max_bytes = payload["resource_estimate"].get("max_public_artifact_bytes")
    if not isinstance(max_bytes, int):
        return payload

    return _apply_public_artifact_byte_cap(
        payload,
        max_public_artifact_bytes=max_bytes,
        artifact_name="split evidence",
    )


def _apply_public_artifact_byte_cap(
    payload: dict[str, Any],
    *,
    max_public_artifact_bytes: int,
    artifact_name: str,
) -> dict[str, Any]:
    while True:
        size = len(canonical_json_bytes(payload, pretty=True))
        if payload["resource_estimate"].get("public_artifact_bytes") == size:
            break
        payload["resource_estimate"]["public_artifact_bytes"] = size
    if size > max_public_artifact_bytes:
        raise ValueError(f"{artifact_name} exceeds split.max_public_artifact_bytes")
    return payload


def _time_row(row: pd.Series) -> dict[str, str | None]:
    return {str(column): _public_time_value(value) for column, value in row.items()}


def _public_time_value(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _signals_frame(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    return pd.concat({"entry": entries, "exit": exits}, axis=1)
