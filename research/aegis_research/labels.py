from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import LabelConfig, to_builtin
from research.aegis_research.data_schema import table_shape

LABEL_TARGET_SCHEMA_VERSION = "label_target.v1"
DIAGNOSTIC_DISTRIBUTION_MAX_VALUES = 50

TRENDLB_MODE_NATIVE_VALUES = {
    "binary": "binary",
    "binary_cont": "binarycont",
    "binary_cont_sat": "binarycontsat",
    "pct_change": "pctchange",
    "pct_change_norm": "pctchangenorm",
}


@dataclass(frozen=True)
class LabelResult:
    labels: pd.DataFrame
    metadata: dict[str, Any]
    native_labels: pd.DataFrame
    lineage: dict[str, Any]
    diagnostics: dict[str, Any]
    target_schema: dict[str, Any]
    split_safety: dict[str, Any]
    native_object: Any | None = None


def build_labels(
    close: pd.DataFrame,
    config: LabelConfig,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return build_label_result(close, config, high=high, low=low).labels


def build_label_result(
    close: pd.DataFrame,
    config: LabelConfig,
    high: pd.DataFrame | None = None,
    low: pd.DataFrame | None = None,
) -> LabelResult:
    native_object = _run_native_label_generator(close, config, high=high, low=low)
    native_labels = _label_panel(native_object.labels)
    selected_params = _selected_params(config)
    selected_native = _select_native_target(native_labels, close, config.kind, selected_params)
    target = _derive_target(selected_native, config)
    target_kind = _target_kind(config)
    split_safety = _split_safety(config, target, selected_params)
    diagnostics = {
        "native": _frame_diagnostics(native_labels),
        "target": _frame_diagnostics(target),
        "unavailable_target_rows": split_safety["unavailable_target_rows"],
    }
    lineage = _lineage(config, selected_params, target)
    target_schema = _target_schema(
        config, selected_params, target, target_kind, diagnostics, split_safety
    )
    metadata = {
        "kind": config.kind,
        "generator": {
            "kind": config.generator.kind,
            "params": config.generator.params,
        },
        "target": {
            "kind": target_kind,
            "role": config.target.role,
            "transform": {
                "name": config.target.transform.name,
                "version": config.target.transform.version,
                "params": config.target.transform.params,
            },
            "selected_params": selected_params,
        },
        "native_output_shape": table_shape(native_labels),
        "output_shape": table_shape(target),
        "split_safety": split_safety,
    }
    return LabelResult(
        labels=target,
        native_object=native_object,
        native_labels=native_labels,
        metadata=metadata,
        lineage=lineage,
        diagnostics=diagnostics,
        target_schema=target_schema,
        split_safety=split_safety,
    )


def _run_native_label_generator(
    close: pd.DataFrame,
    config: LabelConfig,
    *,
    high: pd.DataFrame | None,
    low: pd.DataFrame | None,
) -> Any:
    params = config.generator.params
    if config.kind == "fixlb":
        return vbt.FIXLB.run(
            close,
            n=params["n"],
            hide_params=None,
            hide_default=False,
        )
    if config.kind == "trendlb":
        high_values, low_values = _require_high_low(high, low)
        return vbt.TRENDLB.run(
            high_values,
            low_values,
            params["up_th"],
            params["down_th"],
            mode=TRENDLB_MODE_NATIVE_VALUES[str(params["mode"])],
            hide_params=None,
            hide_default=False,
        )
    if config.kind == "pivotlb":
        high_values, low_values = _require_high_low(high, low)
        return vbt.PIVOTLB.run(
            high_values,
            low_values,
            params["up_th"],
            params["down_th"],
            hide_params=None,
            hide_default=False,
        )
    raise ValueError(f"Unsupported label kind: {config.kind}")


def _selected_params(config: LabelConfig) -> dict[str, Any]:
    selected = dict(config.target.select.params)
    param_keys = set(_native_param_level_names(config.kind))
    for key, value in config.generator.params.items():
        if key not in param_keys:
            continue
        if key not in selected:
            selected[key] = value[0] if isinstance(value, list) else value
    if config.kind == "trendlb" and "mode" in selected:
        selected["mode"] = TRENDLB_MODE_NATIVE_VALUES[str(selected["mode"])]
    return selected


def _select_native_target(
    native_labels: pd.DataFrame,
    close: pd.DataFrame,
    kind: str,
    selected_params: dict[str, Any],
) -> pd.DataFrame:
    param_level_names = _native_param_level_names(kind)
    columns = native_labels.columns
    if isinstance(columns, pd.MultiIndex):
        selected_columns = columns
        for config_key, level_name in param_level_names.items():
            if level_name not in columns.names:
                continue
            value = selected_params[config_key]
            selected_columns = selected_columns[
                selected_columns.get_level_values(level_name) == value
            ]
        selected = native_labels.loc[:, selected_columns]
        levels_to_drop = [
            name for name in param_level_names.values() if name in selected.columns.names
        ]
        if levels_to_drop:
            selected = selected.copy()
            if len(levels_to_drop) == selected.columns.nlevels:
                if len(close.columns) != 1 or len(selected.columns) != 1:
                    raise ValueError("Selected label target must retain a symbol level")
                selected.columns = close.columns
            else:
                selected.columns = selected.columns.droplevel(levels_to_drop)
    else:
        level_name = columns.name
        selected = native_labels
        for config_key, param_level_name in param_level_names.items():
            if level_name == param_level_name:
                value = selected_params[config_key]
                if value not in columns:
                    raise ValueError(
                        f"Selected target parameter {config_key}={value!r} is absent from native labels"
                    )
                selected = native_labels.loc[:, [value]].copy()
                selected.columns = close.columns
                break

    if isinstance(selected.columns, pd.MultiIndex):
        if selected.columns.nlevels != 1:
            raise ValueError("Selected label target must resolve to symbol columns only")
        selected.columns = selected.columns.get_level_values(0)
    if len(selected.columns) != len(close.columns) or selected.columns.duplicated().any():
        raise ValueError("Selected label target must resolve one native slice per symbol")
    if set(map(str, selected.columns)) != set(map(str, close.columns)):
        if len(close.columns) == 1 and len(selected.columns) == 1:
            selected = selected.copy()
            selected.columns = close.columns
        else:
            raise ValueError(
                "Selected label symbols must match close symbols: "
                f"labels={list(map(str, selected.columns))}, close={list(map(str, close.columns))}"
            )
    return selected.reindex(columns=close.columns)


def _derive_target(values: pd.DataFrame, config: LabelConfig) -> pd.DataFrame:
    transform = config.target.transform
    if transform.name == "threshold_future_return":
        threshold = float(transform.params.get("threshold", 0.0))
        target = (values > threshold).astype("Int8").mask(values.isna(), pd.NA)
        return _label_panel(target)
    if transform.name in {"identity_binary", "positive_event"}:
        positive_value = int(transform.params.get("positive_value", 1))
        target = (values == positive_value).astype("Int8").mask(values.isna(), pd.NA)
        return _label_panel(target)
    if transform.name == "continuous_identity":
        return _label_panel(values.astype(float))
    raise ValueError(f"Unsupported label target transform: {transform.name}")


def _target_kind(config: LabelConfig) -> str:
    if config.target.role == "regime":
        return "regime"
    if config.target.transform.name == "continuous_identity":
        return "continuous"
    if config.target.transform.name == "positive_event":
        return "sparse_event"
    return "binary_classification"


def _split_safety(
    config: LabelConfig,
    target: pd.DataFrame,
    selected_params: dict[str, Any],
) -> dict[str, Any]:
    unavailable_rows = int(target.isna().all(axis=1).sum())
    if config.kind == "fixlb":
        horizon = int(selected_params["n"])
        return {
            "prediction_time": "bar_timestamp",
            "evaluation_time": {"kind": "fixed_horizon", "horizon_bars": horizon},
            "unavailable_target_rows": unavailable_rows,
            "purging_required": True,
            "purging_applied": False,
            "leakage_risk": "fixed_unpurged",
            "validation_suitability": "non_decision_grade_until_purged_cv",
        }
    return {
        "prediction_time": "bar_timestamp",
        "evaluation_time": {"kind": "variable_unknown"},
        "unavailable_target_rows": unavailable_rows,
        "purging_required": True,
        "purging_applied": False,
        "leakage_risk": "variable_unknown",
        "validation_suitability": "non_decision_grade_until_purged_cv",
    }


def _lineage(
    config: LabelConfig,
    selected_params: dict[str, Any],
    target: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "generator_kind": config.generator.kind,
        "native_output": config.target.source_output,
        "generator_params": config.generator.params,
        "selected_params": selected_params,
        "target_transform": {
            "name": config.target.transform.name,
            "version": config.target.transform.version,
            "params": config.target.transform.params,
        },
        "symbol_level_name": "symbol",
        "target_panel_columns": list(map(str, target.columns)),
    }


def _target_schema(
    config: LabelConfig,
    selected_params: dict[str, Any],
    target: pd.DataFrame,
    target_kind: str,
    diagnostics: dict[str, Any],
    split_safety: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": LABEL_TARGET_SCHEMA_VERSION,
        "target_kind": target_kind,
        "target_role": config.target.role,
        "source": {
            "generator_kind": config.generator.kind,
            "native_output": config.target.source_output,
            "native_params": config.generator.params,
            "selected_params": selected_params,
            "symbol_level_name": "symbol",
        },
        "transform": {
            "name": config.target.transform.name,
            "version": config.target.transform.version,
            "params": config.target.transform.params,
        },
        "panel": {
            "shape": table_shape(target),
            "symbols": list(map(str, target.columns)),
            "dtypes": {str(column): str(dtype) for column, dtype in target.dtypes.items()},
        },
        "diagnostics": diagnostics,
        "split_safety": split_safety,
        "model_compatibility": _pre_split_model_compatibility(config, target_kind),
    }


def _pre_split_model_compatibility(config: LabelConfig, target_kind: str) -> dict[str, Any]:
    compatible = (
        config.target.role == "supervised_target" and target_kind == "binary_classification"
    )
    return {
        "stage": "pre_split",
        "compatible_with_current_model": compatible,
        "required_model_kind": "logistic_regression",
        "reason": None
        if compatible
        else "current model requires supervised binary classification target",
    }


def _frame_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    missing_count = int(frame.isna().sum().sum())
    valid_count = int(frame.size - missing_count)
    numeric_frame = frame.apply(pd.to_numeric, errors="coerce")
    numeric_count = int(numeric_frame.notna().sum().sum())
    distribution, distribution_omitted = _frame_distribution(frame)
    return {
        "shape": table_shape(frame),
        "missing_count": missing_count,
        "valid_count": valid_count,
        "distribution": distribution,
        "distribution_omitted": distribution_omitted,
        "summary": {
            "min": _frame_numeric_min(numeric_frame, numeric_count),
            "max": _frame_numeric_max(numeric_frame, numeric_count),
            "mean": _frame_numeric_mean(numeric_frame, numeric_count),
        },
    }


def _frame_distribution(frame: pd.DataFrame) -> tuple[dict[str, int], bool]:
    distribution: dict[str, int] = {}
    for column_index in range(len(frame.columns)):
        values = frame.iloc[:, column_index]
        counts = values.dropna().value_counts(dropna=False)
        for key, value in counts.items():
            distribution_key = str(to_builtin(key))
            if (
                distribution_key not in distribution
                and len(distribution) >= DIAGNOSTIC_DISTRIBUTION_MAX_VALUES
            ):
                return {}, True
            distribution[distribution_key] = distribution.get(distribution_key, 0) + int(value)
    return dict(sorted(distribution.items())), False


def _frame_numeric_min(frame: pd.DataFrame, count: int) -> float | None:
    if not count:
        return None
    return float(frame.min(skipna=True).min(skipna=True))


def _frame_numeric_max(frame: pd.DataFrame, count: int) -> float | None:
    if not count:
        return None
    return float(frame.max(skipna=True).max(skipna=True))


def _frame_numeric_mean(frame: pd.DataFrame, count: int) -> float | None:
    if not count:
        return None
    return float(frame.sum(skipna=True).sum(skipna=True) / count)


def _label_panel(values: Any) -> pd.DataFrame:
    if isinstance(values, pd.Series):
        return values.to_frame(name=values.name or "label")
    return values


def _native_param_level_names(kind: str) -> dict[str, str]:
    if kind == "fixlb":
        return {"n": "fixlb_n"}
    if kind == "trendlb":
        return {
            "up_th": "trendlb_up_th",
            "down_th": "trendlb_down_th",
            "mode": "trendlb_mode",
        }
    if kind == "pivotlb":
        return {"up_th": "pivotlb_up_th", "down_th": "pivotlb_down_th"}
    return {}


def _require_high_low(
    high: pd.DataFrame | None,
    low: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if high is None or low is None:
        raise ValueError("high and low are required for this VectorBT label generator")
    return high, low
