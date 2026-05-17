from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from research.aegis_research.config import IndicatorConfig, IndicatorSpecConfig
from research.aegis_research.data_schema import index_identity, table_shape
from research.aegis_research.indicator_registry import IndicatorDefinition, get_indicator_definition

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


def build_indicators(close: pd.DataFrame, config: IndicatorConfig) -> pd.DataFrame:
    return build_indicator_result(close, config).frame


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


def build_indicator_result(close: pd.DataFrame, config: IndicatorConfig) -> IndicatorResult:
    model_feature_series: list[pd.Series] = []
    model_feature_columns: list[tuple[str, str, str, str, str, str]] = []
    native_objects: dict[str, Any] = {}
    native_outputs: dict[str, dict[str, pd.DataFrame]] = {}
    lineage: list[dict[str, Any]] = []
    feature_mapping: dict[str, dict[str, Any]] = {}
    spec_metadata: list[dict[str, Any]] = []

    for spec in config.specs:
        definition = get_indicator_definition(spec.id)
        if not definition.bar_aligned:
            raise ValueError(f"Indicator {spec.id!r} must be bar-aligned in schema v1")

        params = {**definition.default_params, **spec.params}
        combinations = _parameter_combinations(definition, params, spec.param_product)
        outputs, native_object = _run_indicator_definition(close, spec, definition, params)
        if native_object is not None:
            native_objects[spec.id] = native_object
        native_outputs[spec.id] = outputs

        selected_outputs = spec.outputs or list(definition.default_outputs)
        for output_name in selected_outputs:
            if output_name not in outputs:
                raise ValueError(f"Indicator {spec.id!r} did not produce output {output_name!r}")
            _assert_bar_aligned(close, outputs[output_name], spec.id, output_name)

        for feature_spec in spec.model_features or _default_model_features(definition):
            output_name = feature_spec.output
            if output_name not in outputs:
                raise ValueError(f"Indicator {spec.id!r} did not produce output {output_name!r}")
            output_frame = outputs[output_name]
            for column in output_frame.columns:
                params_for_column, symbol = _column_lineage_values(column, output_frame, definition)
                values = _apply_transform(
                    close,
                    output_frame[column],
                    symbol=symbol,
                    transform=feature_spec.transform,
                )
                params_token = _params_token(params_for_column)
                feature_name = _feature_name(
                    spec.id,
                    output_name,
                    feature_spec.transform,
                    params_for_column,
                )
                model_feature_series.append(values.rename(feature_name))
                model_feature_columns.append(
                    (feature_name, spec.id, output_name, feature_spec.transform, params_token, symbol)
                )
                lineage_record = {
                    "feature": feature_name,
                    "indicator_id": spec.id,
                    "kind": definition.kind,
                    "output": output_name,
                    "transform": feature_spec.transform,
                    "params": params_for_column,
                    "symbol": symbol,
                }
                lineage.append(lineage_record)
                feature_mapping.setdefault(
                    feature_name,
                    {
                        "indicator_id": spec.id,
                        "kind": definition.kind,
                        "output": output_name,
                        "transform": feature_spec.transform,
                        "params": params_for_column,
                    },
                )

        spec_metadata.append(
            {
                "id": spec.id,
                "kind": definition.kind,
                "grid": spec.grid,
                "param_product": spec.param_product,
                "parameter_combinations": combinations,
                "grid_size": len(combinations),
                "outputs": selected_outputs,
                "model_features": [
                    {"output": feature.output, "transform": feature.transform}
                    for feature in spec.model_features or _default_model_features(definition)
                ],
                "native_output_shapes": {
                    output_name: table_shape(output_frame)
                    for output_name, output_frame in outputs.items()
                },
            }
        )

    if not model_feature_series:
        raise ValueError("At least one model feature must be configured")

    frame = pd.concat(model_feature_series, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(model_feature_columns, names=FEATURE_COLUMN_NAMES)
    diagnostics = _indicator_diagnostics(frame, lineage)

    return IndicatorResult(
        frame=frame,
        native_objects=native_objects,
        native_outputs=native_outputs,
        lineage=lineage,
        feature_mapping=feature_mapping,
        diagnostics=diagnostics,
        metadata={
            "invalid_value_policy": config.invalid_value_policy,
            "specs": spec_metadata,
            "shape": table_shape(frame),
            "columns": list(map(str, frame.columns)),
            "feature_count": len(feature_mapping),
            "native_object_ids": sorted(native_objects),
        },
    )


def _run_indicator_definition(
    close: pd.DataFrame,
    spec: IndicatorSpecConfig,
    definition: IndicatorDefinition,
    params: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], Any | None]:
    if definition.kind == "primitive":
        return _run_primitive_indicator(close, definition, params), None
    if definition.indicator_class is None:
        raise ValueError(f"Indicator {definition.id!r} has no VectorBT indicator class")

    run_kwargs = {**definition.default_run_kwargs}
    if spec.param_product:
        run_kwargs["param_product"] = True
    native_object = definition.indicator_class.run(close, **params, **run_kwargs)
    outputs = {
        output_name: _normalize_output_frame(
            getattr(native_object, output_name),
            close=close,
            definition=definition,
        )
        for output_name in definition.output_names
        if hasattr(native_object, output_name)
    }
    return outputs, native_object


def _run_primitive_indicator(
    close: pd.DataFrame,
    definition: IndicatorDefinition,
    params: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    columns: list[tuple[Any, str]] = []
    values: list[pd.Series] = []
    close_returns = close.pct_change() if definition.id == "volatility" else None
    for combination in _parameter_combinations(definition, params, param_product=False):
        window = int(combination["window"])
        if definition.id == "returns":
            output = close.pct_change(window)
            output_name = "returns"
        elif definition.id == "volatility":
            output = close_returns.rolling(window).std()
            output_name = "volatility"
        else:
            raise ValueError(f"Unsupported primitive indicator: {definition.id}")
        for symbol in _symbols(close):
            columns.append((window, str(symbol)))
            values.append(output[symbol])
    frame = pd.concat(values, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(
        columns,
        names=[f"{definition.id}_window", "symbol"],
    )
    frames[output_name] = frame
    return frames


def _normalize_output_frame(
    output: pd.Series | pd.DataFrame,
    *,
    close: pd.DataFrame,
    definition: IndicatorDefinition,
) -> pd.DataFrame:
    frame = output.to_frame() if isinstance(output, pd.Series) else output.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        columns = [column if isinstance(column, tuple) else (column,) for column in frame.columns]
        names = list(frame.columns.names)
    else:
        columns = [(column,) for column in frame.columns]
        names = [frame.columns.name]

    expected_param_levels = len(definition.param_names)
    if "symbol" not in names:
        if len(names) == expected_param_levels:
            if len(_symbols(close)) != 1:
                raise ValueError(f"Indicator {definition.id!r} output is missing a symbol level")
            symbol = str(_symbols(close)[0])
            columns = [(*column, symbol) for column in columns]
            names = [*names, "symbol"]
        else:
            names[-1] = "symbol"

    names = [
        f"{definition.id}_{name}" if name in definition.param_names else name
        for name in names
    ]
    frame.columns = pd.MultiIndex.from_tuples(columns, names=names)
    return frame


def _column_lineage_values(
    column: Any,
    frame: pd.DataFrame,
    definition: IndicatorDefinition,
) -> tuple[dict[str, Any], str]:
    values = column if isinstance(column, tuple) else (column,)
    params: dict[str, Any] = {}
    symbol: str | None = None
    for name, value in zip(frame.columns.names, values, strict=True):
        if name == "symbol":
            symbol = str(value)
            continue
        for param_name in definition.param_names:
            if name == f"{definition.id}_{param_name}" or name.endswith(f"_{param_name}"):
                params[param_name] = _native_scalar(value)
                break
    if symbol is None:
        raise ValueError(f"Indicator {definition.id!r} output is missing a symbol level")
    return params, symbol


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


def _parameter_combinations(
    definition: IndicatorDefinition,
    params: dict[str, Any],
    param_product: bool,
) -> list[dict[str, Any]]:
    missing_params = [name for name in definition.param_names if name not in params]
    if missing_params:
        raise ValueError(f"Indicator {definition.id!r} missing params: {missing_params}")
    value_lists = [_as_list(params[name]) for name in definition.param_names]
    if param_product:
        rows = itertools.product(*value_lists)
    else:
        length = max(len(values) for values in value_lists)
        rows = zip(
            *[
                values * length if len(values) == 1 else values
                for values in value_lists
            ],
            strict=True,
        )
    return [
        {name: _native_scalar(value) for name, value in zip(definition.param_names, row, strict=True)}
        for row in rows
    ]


def _default_model_features(definition: IndicatorDefinition):
    from research.aegis_research.config import IndicatorFeatureConfig

    return [
        IndicatorFeatureConfig(output=feature["output"], transform=feature.get("transform", "identity"))
        for feature in definition.default_model_features
    ]


def _assert_bar_aligned(
    close: pd.DataFrame,
    output: pd.DataFrame,
    indicator_id: str,
    output_name: str,
) -> None:
    if not output.index.equals(close.index):
        raise ValueError(f"Indicator {indicator_id!r} output {output_name!r} is not bar-aligned")
    output_symbols = set(map(str, output.columns.get_level_values("symbol")))
    input_symbols = set(map(str, _symbols(close)))
    if output_symbols != input_symbols:
        raise ValueError(f"Indicator {indicator_id!r} output {output_name!r} symbols do not match input")


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


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


def _symbols(close: pd.DataFrame) -> list[Any]:
    return list(close.columns)


def _native_scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value
