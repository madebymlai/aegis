from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from research.aegis_research.config import ModelConfig, to_builtin
from research.aegis_research.model_contracts import (
    POSITIVE_CLASS_PROBABILITY,
    ModelDataset,
    ModelExecutionContext,
    ModelFitResult,
    ModelPluginDefinition,
    ModelPredictionResult,
)
from research.aegis_research.model_registry import FrozenModelRegistry, ModelRegistryError
from research.aegis_research.splits import ValidationSplit, split_purging_passed

LABEL_COLUMN = "__label__"
MODEL_METADATA_SCHEMA_VERSION = "model_metadata.v1"


class TargetModelCompatibilityError(ValueError):
    def __init__(self, diagnostics: dict[str, Any]) -> None:
        self.diagnostics = diagnostics
        super().__init__(str(diagnostics.get("failure_reason", "target/model incompatible")))


@dataclass(frozen=True)
class TrainedModel:
    plugin_id: str
    state: Any
    definition: ModelPluginDefinition
    params: Mapping[str, Any]
    metadata: dict[str, Any]


def train_model(
    indicators: pd.DataFrame,
    labels: pd.DataFrame,
    config: ModelConfig,
    *,
    model_registry: FrozenModelRegistry,
    target_schema: Mapping[str, Any],
    split_label: str,
) -> TrainedModel:
    definition = _model_definition(config, model_registry)
    _assert_supported_target(definition, target_schema)
    training = _training_dataset(indicators, labels)
    usable = training.usable_frame
    if len(usable) < config.min_train_samples:
        raise ValueError(
            f"Need at least {config.min_train_samples} train samples, got {len(usable)}"
        )

    target = usable[LABEL_COLUMN]
    class_counts = _class_counts(target)
    if len(class_counts) < 2:
        raise ValueError("training target must contain both classes")

    feature_columns = tuple(training.feature_columns)
    dataset = ModelDataset(
        features=usable.loc[:, feature_columns],
        target=target,
        row_index=usable.index,
        metadata=training.metadata,
    )
    context = ModelExecutionContext(
        plugin_id=definition.declaration.id,
        split_label=split_label,
        set_name="train",
        target_schema=target_schema,
        feature_columns=feature_columns,
    )
    fit_result = definition.plugin.fit(dataset, params=config.params, context=context)
    _validate_fit_result(fit_result, target_schema)

    metadata = _model_metadata(
        definition,
        model_registry,
        config,
        target_schema,
        split_label=split_label,
        training=training,
        usable=usable,
        fit_result=fit_result,
    )
    return TrainedModel(
        plugin_id=definition.declaration.id,
        state=fit_result.state,
        definition=definition,
        params=dict(config.params),
        metadata=metadata,
    )


def predict_positive_class_probability(
    model: TrainedModel,
    indicators: pd.DataFrame,
    *,
    target_schema: Mapping[str, Any],
    split_label: str,
    set_name: str,
) -> pd.DataFrame:
    stacked = _stack_indicator_panel(indicators)
    expected_columns = tuple(model.metadata["features"]["columns"])
    _assert_prediction_features(stacked, expected_columns)
    usable = stacked.loc[:, expected_columns].dropna()
    probabilities = pd.Series(
        index=stacked.index,
        dtype=float,
        name=POSITIVE_CLASS_PROBABILITY,
    )
    if not usable.empty:
        dataset = ModelDataset(
            features=usable,
            target=None,
            row_index=usable.index,
            metadata={"rows": len(usable), "set": set_name},
        )
        context = ModelExecutionContext(
            plugin_id=model.plugin_id,
            split_label=split_label,
            set_name=set_name,
            target_schema=target_schema,
            feature_columns=expected_columns,
        )
        result = model.definition.plugin.predict(
            model.state,
            dataset,
            params=model.params,
            context=context,
        )
        positive = _positive_probability_series(result, target_schema)
        _assert_probability_index(positive, usable.index)
        _assert_probability_values(positive)
        probabilities.loc[usable.index] = positive.astype(float).to_numpy()
    return probabilities.unstack("symbol").reindex(index=indicators.index)


def target_model_compatibility(
    labels: pd.DataFrame,
    config: ModelConfig,
    target_schema: dict[str, Any],
    splits: list[ValidationSplit] | None = None,
    *,
    phase: str,
    split_metadata: dict[str, Any] | None = None,
    model_registry: FrozenModelRegistry | None = None,
) -> dict[str, Any]:
    split_safety = _effective_split_safety(
        target_schema.get("split_safety", {}),
        split_metadata,
    )
    diagnostics: dict[str, Any] = {
        "phase": phase,
        "compatible": True,
        "target_kind": target_schema.get("target_kind"),
        "target_role": target_schema.get("target_role"),
        "model_plugin_id": config.plugin_id,
        "split_safety": split_safety,
        "splits": [],
        "failure_reason": None,
    }
    try:
        definition = _model_definition(config, model_registry)
    except ValueError as error:
        return _incompatible(diagnostics, str(error))
    diagnostics["plugin"] = _declaration_payload(definition)

    if target_schema.get("target_role") not in definition.declaration.supported_target_roles:
        return _incompatible(
            diagnostics,
            "model plugin requires target role 'supervised_target'",
        )
    if target_schema.get("target_kind") not in definition.declaration.supported_target_kinds:
        return _incompatible(
            diagnostics,
            "model plugin requires binary classification target",
        )
    if POSITIVE_CLASS_PROBABILITY not in definition.declaration.prediction_outputs:
        return _incompatible(
            diagnostics,
            f"model plugin must emit {POSITIVE_CLASS_PROBABILITY}",
        )
    try:
        _target_class_contract(target_schema)
    except ValueError as error:
        return _incompatible(diagnostics, str(error))
    if not isinstance(labels, pd.DataFrame) or isinstance(labels.columns, pd.MultiIndex):
        return _incompatible(diagnostics, "selected target must be a timestamp-by-symbol panel")
    if phase == "post_split" and _requires_purging_proof(split_safety):
        return _incompatible(
            diagnostics,
            "look-ahead labels require purged split evidence before validation",
        )

    if splits is None:
        return diagnostics

    stacked_labels = _stack_label_panel(labels).dropna()
    label_times = stacked_labels.index.get_level_values(0)
    for split in splits:
        if len(split.train_index) == 0 or len(split.test_index) == 0:
            return _incompatible(
                diagnostics,
                f"Split {split.label} produced an empty train or test range",
            )
        values = stacked_labels[label_times.isin(split.train_index)]
        test_values = stacked_labels[label_times.isin(split.test_index)]
        class_counts = _class_counts(values)
        test_class_counts = _class_counts(test_values)
        diagnostics["splits"].append(
            {
                "label": split.label,
                "train_class_counts": class_counts,
                "test_class_counts": test_class_counts,
            }
        )
        if len(class_counts) < 2:
            return _incompatible(
                diagnostics,
                f"Split {split.label} training target must contain both classes",
            )
    return diagnostics


def assert_target_model_compatible(diagnostics: dict[str, Any]) -> None:
    if not diagnostics.get("compatible", False):
        raise TargetModelCompatibilityError(diagnostics)


@dataclass(frozen=True)
class _TrainingDataset:
    frame: pd.DataFrame
    usable_frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    metadata: dict[str, Any]


def _training_dataset(
    indicators: pd.DataFrame,
    labels: pd.DataFrame,
) -> _TrainingDataset:
    _validate_feature_label_symbols(indicators, labels)
    features = _stack_indicator_panel(indicators, symbols=labels.columns)
    label_values = _stack_label_panel(labels)
    frame = features.join(label_values.rename(LABEL_COLUMN))
    usable = frame.dropna()
    feature_columns = tuple(features.columns)
    return _TrainingDataset(
        frame=frame,
        usable_frame=usable,
        feature_columns=feature_columns,
        metadata={
            "rows": len(frame),
            "usable_rows": len(usable),
            "dropped_rows": len(frame) - len(usable),
            "symbols": [str(symbol) for symbol in labels.columns],
            "per_symbol_rows": _per_symbol_counts(frame),
            "per_symbol_usable_rows": _per_symbol_counts(usable),
            "feature_columns": list(feature_columns),
        },
    )


def _stack_indicator_panel(
    indicators: pd.DataFrame,
    *,
    symbols: pd.Index | None = None,
) -> pd.DataFrame:
    if not _has_symbol_level(indicators):
        raise ValueError("indicator columns must include a symbol level")

    symbol_level = indicators.columns.names.index("symbol")
    if symbols is None:
        symbols = indicators.columns.get_level_values(symbol_level).unique()
    available_symbols = set(indicators.columns.get_level_values(symbol_level))
    missing_symbols = [symbol for symbol in symbols if symbol not in available_symbols]
    if missing_symbols:
        raise ValueError(f"indicator features are missing symbols: {missing_symbols}")

    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        symbol_features = indicators.xs(symbol, axis=1, level="symbol", drop_level=True)
        symbol_features = symbol_features.copy()
        if (
            isinstance(symbol_features.columns, pd.MultiIndex)
            and "feature" in symbol_features.columns.names
        ):
            symbol_features.columns = symbol_features.columns.get_level_values("feature")
        else:
            symbol_features.columns = [
                "__".join(map(str, column)) if isinstance(column, tuple) else str(column)
                for column in symbol_features.columns
            ]
        if symbol_features.columns.duplicated().any():
            duplicates = sorted(set(symbol_features.columns[symbol_features.columns.duplicated()]))
            raise ValueError(f"indicator feature names collide: {duplicates}")
        symbol_features.index = pd.MultiIndex.from_arrays(
            [symbol_features.index, [symbol] * len(symbol_features)],
            names=[indicators.index.name, "symbol"],
        )
        frames.append(symbol_features)
    return pd.concat(frames).sort_index()


def _stack_label_panel(labels: pd.DataFrame) -> pd.Series:
    stacked = labels.stack()
    stacked.index = stacked.index.set_names([labels.index.name, "symbol"])
    return stacked


def _has_symbol_level(indicators: pd.DataFrame) -> bool:
    return isinstance(indicators.columns, pd.MultiIndex) and "symbol" in indicators.columns.names


def _validate_feature_label_symbols(indicators: pd.DataFrame, labels: pd.DataFrame) -> None:
    if not _has_symbol_level(indicators):
        raise ValueError("indicator columns must include a symbol level")
    symbol_level = indicators.columns.names.index("symbol")
    feature_symbols = set(map(str, indicators.columns.get_level_values(symbol_level)))
    label_symbols = set(map(str, labels.columns))
    if feature_symbols != label_symbols:
        raise ValueError(
            "indicator feature symbols must match labels: "
            f"features={sorted(feature_symbols)}, labels={sorted(label_symbols)}"
        )


def _model_definition(
    config: ModelConfig,
    model_registry: FrozenModelRegistry | None,
) -> ModelPluginDefinition:
    if model_registry is None:
        raise ModelRegistryError("registered model plugin registry is required")
    if config.plugin_id is None:
        raise ModelRegistryError("model.plugin_id is required")
    return model_registry.get(config.plugin_id)


def _assert_supported_target(
    definition: ModelPluginDefinition,
    target_schema: Mapping[str, Any],
) -> None:
    target_role = target_schema.get("target_role")
    target_kind = target_schema.get("target_kind")
    if target_role not in definition.declaration.supported_target_roles:
        raise ValueError(f"model plugin does not support target role: {target_role}")
    if target_kind not in definition.declaration.supported_target_kinds:
        raise ValueError(f"model plugin does not support target kind: {target_kind}")
    _target_class_contract(target_schema)


def _validate_fit_result(
    fit_result: ModelFitResult,
    target_schema: Mapping[str, Any],
) -> None:
    _validated_probability_mapping(
        fit_result.observed_classes,
        fit_result.class_probability_columns,
        target_schema,
    )


def _positive_probability_series(
    result: ModelPredictionResult,
    target_schema: Mapping[str, Any],
) -> pd.Series:
    mapping = _validated_probability_mapping(
        result.observed_classes,
        result.class_probability_columns,
        target_schema,
    )
    positive_canonical = _target_class_contract(target_schema)["positive_canonical"]
    column_name = mapping[positive_canonical]
    if isinstance(result.probabilities, pd.Series):
        if result.probabilities.name not in {column_name, POSITIVE_CLASS_PROBABILITY}:
            raise ValueError(
                "prediction probability series name must match the mapped positive class output"
            )
        series = result.probabilities.copy()
    else:
        if column_name not in result.probabilities.columns:
            raise ValueError(
                f"prediction output is missing positive class probability column {column_name!r}"
            )
        series = result.probabilities[column_name].copy()
    series.name = POSITIVE_CLASS_PROBABILITY
    return series


def _validated_probability_mapping(
    observed_classes: tuple[Any, ...],
    class_probability_columns: Mapping[Any, str],
    target_schema: Mapping[str, Any],
) -> dict[str, str]:
    target_contract = _target_class_contract(target_schema)
    positive = target_contract["positive_canonical"]
    observed = [_canonical_class_label(value) for value in observed_classes]
    if len(set(observed)) != len(observed):
        raise ValueError("plugin observed classes contain duplicate canonical labels")
    if positive not in observed:
        raise ValueError("plugin observed classes do not include target positive_class")

    mapping: dict[str, str] = {}
    for class_label, column in class_probability_columns.items():
        canonical = _canonical_class_label(class_label)
        if canonical in mapping:
            raise ValueError("class probability mapping contains duplicate canonical labels")
        if not isinstance(column, str) or not column:
            raise ValueError("class probability mapping columns must be non-empty strings")
        mapping[canonical] = column
    if positive not in mapping:
        raise ValueError("class probability mapping omits target positive_class")
    return mapping


def _target_class_contract(target_schema: Mapping[str, Any]) -> dict[str, Any]:
    if target_schema.get("target_kind") != "binary_classification":
        raise ValueError("model plugin requires binary classification target")
    classes = target_schema.get("classes")
    if not isinstance(classes, list) or len(classes) != 2:
        raise ValueError("binary target schema must define exactly two classes")
    canonical_classes: set[str] = set()
    for item in classes:
        if not isinstance(item, Mapping) or "label" not in item:
            raise ValueError("target classes must include labels")
        canonical = str(item.get("canonical") or _canonical_class_label(item["label"]))
        if canonical in canonical_classes:
            raise ValueError("target classes contain duplicate canonical labels")
        canonical_classes.add(canonical)
    if "positive_class" not in target_schema:
        raise ValueError("binary target schema must define positive_class")
    positive_canonical = _canonical_class_label(target_schema["positive_class"])
    if positive_canonical not in canonical_classes:
        raise ValueError("target positive_class is not present in target classes")
    return {"classes": canonical_classes, "positive_canonical": positive_canonical}


def _canonical_class_label(value: Any) -> str:
    if hasattr(value, "item"):
        value = value.item()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"bool:{str(value).lower()}"
    if isinstance(value, int):
        return f"int:{value}"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("class labels must be finite")
        return f"float:{value!r}"
    if isinstance(value, str):
        return f"str:{value}"
    raise ValueError(f"unsupported class label type: {type(value).__name__}")


def _assert_prediction_features(stacked: pd.DataFrame, expected_columns: tuple[str, ...]) -> None:
    actual_columns = tuple(stacked.columns)
    if actual_columns != expected_columns:
        raise ValueError(
            "prediction feature columns must match training feature columns: "
            f"expected={list(expected_columns)}, actual={list(actual_columns)}"
        )


def _assert_probability_index(series: pd.Series, expected_index: pd.MultiIndex) -> None:
    if not series.index.equals(expected_index):
        raise ValueError("prediction probabilities must preserve dataset row index")
    if not isinstance(series.index, pd.MultiIndex) or "symbol" not in series.index.names:
        raise ValueError("prediction probabilities must use a timestamp-symbol index")
    if series.index.has_duplicates:
        raise ValueError("prediction probabilities must not contain duplicate rows")


def _assert_probability_values(series: pd.Series) -> None:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError("prediction probabilities must be finite numeric values")
    if not numeric.map(math.isfinite).all():
        raise ValueError("prediction probabilities must be finite numeric values")
    if ((numeric < 0) | (numeric > 1)).any():
        raise ValueError("prediction probabilities must be within [0, 1]")


def _model_metadata(
    definition: ModelPluginDefinition,
    model_registry: FrozenModelRegistry,
    config: ModelConfig,
    target_schema: Mapping[str, Any],
    *,
    split_label: str,
    training: _TrainingDataset,
    usable: pd.DataFrame,
    fit_result: ModelFitResult,
) -> dict[str, Any]:
    probability_mapping = _validated_probability_mapping(
        fit_result.observed_classes,
        fit_result.class_probability_columns,
        target_schema,
    )
    feature_columns = list(training.feature_columns)
    target = usable[LABEL_COLUMN]
    metadata = {
        "schema_version": MODEL_METADATA_SCHEMA_VERSION,
        "artifact_kind": "validation_split_model",
        "split": split_label,
        "plugin": _declaration_payload(definition),
        "registry_fingerprint": model_registry.fingerprint,
        "config": {
            "plugin_id": config.plugin_id,
            "min_train_samples": config.min_train_samples,
        },
        "target": {
            "schema_version": target_schema.get("schema_version"),
            "target_kind": target_schema.get("target_kind"),
            "target_role": target_schema.get("target_role"),
            "classes": to_builtin(target_schema.get("classes", [])),
            "positive_class": to_builtin(target_schema.get("positive_class")),
            "transform": to_builtin(target_schema.get("transform", {})),
        },
        "probability": {
            "output_name": POSITIVE_CLASS_PROBABILITY,
            "class_probability_columns": probability_mapping,
            "observed_classes": [_canonical_class_label(value) for value in fit_result.observed_classes],
            "calibrated": False,
            "threshold_tuned": False,
        },
        "features": {
            "columns": feature_columns,
            "columns_hash": _hash_json(feature_columns),
            "count": len(feature_columns),
        },
        "training": {
            "rows": len(usable),
            "class_counts": _class_counts(target),
            "per_symbol_rows": _per_symbol_counts(usable),
            "dropped_rows": training.metadata["dropped_rows"],
            "source_rows": training.metadata["rows"],
        },
        "diagnostics": {
            "dataset": training.metadata,
        },
        "trusted_loading": {
            "trusted_native_state": definition.declaration.trusted_loading,
            "state_schema_version": definition.declaration.state_schema_version,
        },
    }
    return to_builtin(metadata)


def _declaration_payload(definition: ModelPluginDefinition) -> dict[str, Any]:
    return to_builtin(asdict(definition.declaration))


def _hash_json(value: Any) -> str:
    data = json.dumps(to_builtin(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _class_counts(values: pd.Series) -> dict[str, int]:
    return {
        _canonical_class_label(key): int(value)
        for key, value in values.value_counts(dropna=False).items()
    }


def _per_symbol_counts(frame: pd.DataFrame) -> dict[str, int]:
    if not isinstance(frame.index, pd.MultiIndex) or "symbol" not in frame.index.names:
        raise ValueError("model diagnostics require a timestamp-symbol MultiIndex")
    counts = frame.groupby(level="symbol", sort=True).size()
    return {str(symbol): int(count) for symbol, count in counts.items()}


def _incompatible(diagnostics: dict[str, Any], reason: str) -> dict[str, Any]:
    return {**diagnostics, "compatible": False, "failure_reason": reason}


def _effective_split_safety(
    split_safety: dict[str, Any],
    split_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    effective = dict(split_safety)
    if split_purging_passed(split_metadata):
        effective["purging_applied"] = True
        effective["leakage_risk"] = "purged_interval_checked"
        effective["validation_suitability"] = "decision_grade_label_purging"
    return effective


def _requires_purging_proof(split_safety: dict[str, Any]) -> bool:
    return bool(split_safety.get("purging_required")) and not bool(
        split_safety.get("purging_applied")
    )
