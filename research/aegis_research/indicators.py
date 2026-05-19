from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import ComponentSelection, FrozenComponentRegistry
from research.aegis_research.component_registry.contracts import (
    ComponentDefinition,
    IndicatorManifest,
)
from research.aegis_research.config import RunIndicatorSourceConfig
from research.aegis_research.data_schema import index_identity, table_shape
from research.aegis_research.market_data.contracts import MarketDataBundle

FEATURE_COLUMN_NAMES = ["feature", "indicator", "output", "transform", "params", "symbol"]


@dataclass(frozen=True)
class IndicatorResult:
    frame: pd.DataFrame
    metadata: dict[str, Any]
    native_objects: dict[str, Any] = field(default_factory=dict)
    native_outputs: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)
    lineage: list[dict[str, Any]] = field(default_factory=list)
    feature_mapping: dict[str, dict[str, Any]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelFeatureMatrix:
    frame: pd.DataFrame
    feature_mapping: dict[str, dict[str, Any]]
    lineage: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    eligible_index: pd.Index
    metadata: dict[str, Any]


def build_component_indicator_result(
    data: MarketDataBundle,
    refs: list[RunIndicatorSourceConfig],
    *,
    component_registry: FrozenComponentRegistry,
    invalid_value_policy: str = "drop_rows",
) -> IndicatorResult:
    component_results = [
        _run_component_indicator(data, definition)
        for definition in _expanded_component_indicator_definitions(refs, component_registry)
    ]
    if not component_results:
        raise ValueError("At least one component indicator must be configured")

    frame = pd.concat([result.frame for result in component_results], axis=1)
    lineage = [item for result in component_results for item in result.lineage]
    feature_mapping = {
        key: value for result in component_results for key, value in result.feature_mapping.items()
    }
    native_outputs = {
        key: value for result in component_results for key, value in result.native_outputs.items()
    }
    native_objects = {
        key: value for result in component_results for key, value in result.native_objects.items()
    }
    return IndicatorResult(
        frame=frame,
        native_objects=native_objects,
        native_outputs=native_outputs,
        lineage=lineage,
        feature_mapping=feature_mapping,
        diagnostics=_indicator_diagnostics(frame, lineage),
        metadata={
            "invalid_value_policy": invalid_value_policy,
            "source": "component",
            "components": [result.metadata for result in component_results],
            "shape": table_shape(frame),
            "columns": list(map(str, frame.columns)),
            "feature_count": len(feature_mapping),
            "native_object_ids": sorted(native_objects),
        },
    )


def build_model_feature_matrix(
    indicator_result: IndicatorResult,
    labels: pd.DataFrame,
    *,
    invalid_value_policy: str | None = None,
) -> ModelFeatureMatrix:
    policy = invalid_value_policy or str(
        indicator_result.metadata.get("invalid_value_policy", "drop_rows")
    )
    if policy not in {"drop_rows", "raise"}:
        raise ValueError(f"Unsupported invalid value policy: {policy}")

    _validate_feature_label_symbols(indicator_result.frame, labels)
    frame = indicator_result.frame.copy()
    inf_mask = frame.isin([float("inf"), float("-inf")])
    total_inf_count = int(inf_mask.sum().sum())
    frame = frame.mask(inf_mask, pd.NA)

    common_index = frame.index.intersection(labels.index)
    if common_index.empty:
        raise ValueError("Feature and label indexes do not overlap")
    feature_rows = frame.loc[common_index]
    label_rows = labels.loc[common_index]
    feature_valid = feature_rows.notna().all(axis=1)
    label_valid = label_rows.notna().all(axis=1)
    eligible_index = common_index[feature_valid & label_valid]
    feature_invalid = ~feature_valid
    label_invalid = ~label_valid
    dropped_count = int(len(common_index) - len(eligible_index))
    if policy == "raise" and dropped_count:
        raise ValueError(f"Invalid feature or label values on {dropped_count} rows")

    symbols = sorted(map(str, labels.columns))
    feature_mapping = {
        feature: {**mapping, "symbol_source": "sample_index", "symbols": symbols}
        for feature, mapping in indicator_result.feature_mapping.items()
    }
    diagnostics = {
        "policy": policy,
        "eligible_index": index_identity(eligible_index),
        "input_index": index_identity(common_index),
        "dropped_row_count": dropped_count,
        "feature_invalid_row_count": int(feature_invalid.sum()),
        "label_invalid_row_count": int(label_invalid.sum()),
        "overlapping_invalid_row_count": int((feature_invalid & label_invalid).sum()),
        "total_inf_count": total_inf_count,
        "total_feature_missing_count": int(feature_rows.isna().sum().sum()),
        "total_label_missing_count": int(label_rows.isna().sum().sum()),
        "features": _model_feature_diagnostics(frame, indicator_result.lineage),
    }
    return ModelFeatureMatrix(
        frame=frame,
        feature_mapping=feature_mapping,
        lineage=indicator_result.lineage,
        diagnostics=diagnostics,
        eligible_index=eligible_index,
        metadata={
            "shape": table_shape(frame),
            "feature_count": len(feature_mapping),
            "symbols": symbols,
            "invalid_value_policy": policy,
        },
    )


def _expanded_component_indicator_definitions(
    refs: list[RunIndicatorSourceConfig],
    component_registry: FrozenComponentRegistry,
) -> list[ComponentDefinition]:
    definitions: list[ComponentDefinition] = []
    seen: set[str] = set()
    for ref in refs:
        if ref.source != "component":
            raise ValueError("train indicators must select component sources")
        component_ids = ref.expanded_ids(component_registry.ids("indicators"))
        for component_id in component_ids:
            if component_id in seen:
                raise ValueError(f"duplicate indicator component ref: {component_id}")
            seen.add(component_id)
            definitions.append(component_registry.get(ComponentSelection("indicators", component_id)))
    return definitions


def _run_component_indicator(data: MarketDataBundle, definition: ComponentDefinition) -> IndicatorResult:
    if not isinstance(definition.manifest, IndicatorManifest):
        raise TypeError(f"component {definition.id!r} is not an indicator")
    output = definition.load_callable()(data)
    if isinstance(output, IndicatorResult):
        return _source_component_indicator_result(output, definition)
    output_name = _single_component_output_name(definition.manifest)
    frame = _component_output_frame(output, data.close, definition.id, output_name)
    return _component_frame_indicator_result(data.close, frame, definition, output_name)


def _source_component_indicator_result(
    result: IndicatorResult,
    definition: ComponentDefinition,
) -> IndicatorResult:
    metadata = {
        **result.metadata,
        "id": definition.id,
        "version": definition.manifest.version,
        "source_hash": definition.identity.source_hash,
    }
    lineage = [{**item, "component_id": definition.id} for item in result.lineage]
    return IndicatorResult(
        frame=result.frame,
        metadata=metadata,
        native_objects={definition.id: result.native_objects},
        native_outputs={definition.id: result.native_outputs},
        lineage=lineage,
        feature_mapping={
            key: {**value, "component_id": definition.id}
            for key, value in result.feature_mapping.items()
        },
        diagnostics=result.diagnostics,
    )


def _component_frame_indicator_result(
    close: pd.DataFrame,
    output_frame: pd.DataFrame,
    definition: ComponentDefinition,
    output_name: str,
) -> IndicatorResult:
    manifest = definition.manifest
    if not isinstance(manifest, IndicatorManifest):
        raise TypeError(f"component {definition.id!r} is not an indicator")
    model_feature_series: list[pd.Series] = []
    model_feature_columns: list[tuple[str, str, str, str, str, str]] = []
    lineage: list[dict[str, Any]] = []
    feature_mapping: dict[str, dict[str, Any]] = {}
    for feature_spec in manifest.default_model_features:
        if feature_spec["output"] != output_name:
            raise ValueError(
                f"indicator component {definition.id!r} did not produce output {feature_spec['output']!r}"
            )
        transform = feature_spec.get("transform", "identity")
        for column in output_frame.columns:
            params, symbol = _component_lineage_values(column, output_frame, manifest)
            values = _apply_transform(close, output_frame[column], symbol=symbol, transform=transform)
            params_token = _params_token(params)
            feature_name = _feature_name(definition.id, output_name, transform, params)
            model_feature_series.append(values.rename(feature_name))
            model_feature_columns.append(
                (feature_name, definition.id, output_name, transform, params_token, symbol)
            )
            lineage_record = {
                "feature": feature_name,
                "indicator_id": definition.id,
                "component_id": definition.id,
                "kind": "component",
                "output": output_name,
                "transform": transform,
                "params": params,
                "symbol": symbol,
            }
            lineage.append(lineage_record)
            feature_mapping.setdefault(
                feature_name,
                {
                    "indicator_id": definition.id,
                    "component_id": definition.id,
                    "kind": "component",
                    "output": output_name,
                    "transform": transform,
                    "params": params,
                },
            )
    frame = pd.concat(model_feature_series, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(model_feature_columns, names=FEATURE_COLUMN_NAMES)
    return IndicatorResult(
        frame=frame,
        metadata={
            "id": definition.id,
            "version": manifest.version,
            "source_hash": definition.identity.source_hash,
            "outputs": [output_name],
            "params": _component_output_params(output_frame, manifest),
            "model_features": list(manifest.default_model_features),
        },
        native_outputs={definition.id: {output_name: output_frame}},
        lineage=lineage,
        feature_mapping=feature_mapping,
        diagnostics={},
    )


def _single_component_output_name(manifest: IndicatorManifest) -> str:
    if len(manifest.default_outputs) != 1:
        raise ValueError("indicator components with multiple default outputs must return IndicatorResult")
    return manifest.default_outputs[0]


def _component_output_frame(
    output: Any,
    close: pd.DataFrame,
    component_id: str,
    output_name: str,
) -> pd.DataFrame:
    frame = output.to_frame() if isinstance(output, pd.Series) else output
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"indicator component {component_id!r} output {output_name!r} must be a pandas object")
    if not frame.index.equals(close.index):
        raise ValueError(f"indicator component {component_id!r} output {output_name!r} is not bar-aligned")
    if isinstance(frame.columns, pd.MultiIndex):
        if "symbol" not in frame.columns.names:
            close_symbols = set(map(str, close.columns))
            last_level_symbols = set(map(str, frame.columns.get_level_values(-1)))
            if last_level_symbols == close_symbols:
                result = frame.copy()
                names = list(result.columns.names)
                names[-1] = "symbol"
                result.columns = result.columns.set_names(names)
                return result
            if len(close.columns) != 1:
                raise ValueError(f"indicator component {component_id!r} output {output_name!r} is missing symbol level")
            symbol = str(close.columns[0])
            result = frame.copy()
            result.columns = pd.MultiIndex.from_tuples(
                [(*column, symbol) for column in result.columns],
                names=[*result.columns.names, "symbol"],
            )
            return result
        return frame
    if list(map(str, frame.columns)) != list(map(str, close.columns)):
        raise ValueError(f"indicator component {component_id!r} output {output_name!r} symbols do not match input")
    result = frame.copy()
    result.columns = pd.MultiIndex.from_tuples([(str(column),) for column in result.columns], names=["symbol"])
    return result


def _component_lineage_values(
    column: Any,
    frame: pd.DataFrame,
    manifest: IndicatorManifest,
) -> tuple[dict[str, Any], str]:
    values = column if isinstance(column, tuple) else (column,)
    params: dict[str, Any] = {}
    symbol: str | None = None
    for name, value in zip(frame.columns.names, values, strict=True):
        if name == "symbol":
            symbol = str(value)
            continue
        for param_name in manifest.param_names:
            if name == param_name or name.endswith(f"_{param_name}"):
                params[param_name] = _native_scalar(value)
                break
    if symbol is None:
        raise ValueError("indicator component output is missing a symbol level")
    return params, symbol


def _component_output_params(
    frame: pd.DataFrame,
    manifest: IndicatorManifest,
) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for column in frame.columns:
        params, _symbol = _component_lineage_values(column, frame, manifest)
        token = _params_token(params)
        if token in seen:
            continue
        seen.add(token)
        rows.append(params)
    return rows


def _apply_transform(
    close: pd.DataFrame,
    values: pd.Series,
    *,
    symbol: str,
    transform: str,
) -> pd.Series:
    if transform == "identity":
        return values
    if transform == "distance_to_close":
        return close[symbol] / values - 1
    if transform == "scale_0_1":
        return values / 100.0
    raise ValueError(f"Unsupported indicator transform: {transform}")


def _indicator_diagnostics(frame: pd.DataFrame, lineage: list[dict[str, Any]]) -> dict[str, Any]:
    feature_rows: list[dict[str, Any]] = []
    for column, lineage_record in zip(frame.columns, lineage, strict=True):
        values = frame[column]
        inf_count = int(values.isin([float("inf"), float("-inf")]).sum())
        missing_count = int(values.isna().sum())
        feature_rows.append(
            {
                **lineage_record,
                "missing_count": missing_count,
                "inf_count": inf_count,
                "valid_count": int(len(values) - missing_count - inf_count),
            }
        )
    return {
        "features": feature_rows,
        "total_missing_count": sum(row["missing_count"] for row in feature_rows),
        "total_inf_count": sum(row["inf_count"] for row in feature_rows),
    }


def _model_feature_diagnostics(
    frame: pd.DataFrame,
    lineage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column, lineage_record in zip(frame.columns, lineage, strict=True):
        values = frame[column]
        rows.append(
            {
                **lineage_record,
                "missing_count": int(values.isna().sum()),
                "valid_count": int(values.notna().sum()),
            }
        )
    return rows


def _validate_feature_label_symbols(features: pd.DataFrame, labels: pd.DataFrame) -> None:
    if not isinstance(features.columns, pd.MultiIndex) or "symbol" not in features.columns.names:
        raise ValueError("Feature columns must include a symbol level")
    feature_symbols = set(map(str, features.columns.get_level_values("symbol")))
    label_symbols = set(map(str, labels.columns))
    if feature_symbols != label_symbols:
        raise ValueError(
            "Feature and label symbols must match: "
            f"features={sorted(feature_symbols)}, labels={sorted(label_symbols)}"
        )


def _feature_name(
    indicator_id: str,
    output: str,
    transform: str,
    params: dict[str, Any],
) -> str:
    parts = [indicator_id, output, transform]
    parts.extend(f"{key}_{params[key]}" for key in sorted(params))
    return "__".join(_slug(part) for part in parts)


def _params_token(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def _slug(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")


def _native_scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value
