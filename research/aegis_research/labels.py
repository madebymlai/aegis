from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import LabelConfig
from research.aegis_research.data_schema import table_shape


@dataclass(frozen=True)
class LabelResult:
    labels: pd.DataFrame
    metadata: dict[str, Any]
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
    if config.kind == "fixlb":
        fixlb = vbt.FIXLB.run(close, n=config.horizon, hide_params=True)
        labels = _binary_from_numeric_labels(fixlb.labels, config.threshold)
        return LabelResult(
            labels=labels,
            native_object=fixlb,
            metadata={
                "kind": config.kind,
                "horizon": config.horizon,
                "threshold": config.threshold,
                "output_shape": table_shape(labels),
            },
        )
    if config.kind == "trendlb":
        high_values, low_values = _require_high_low(high, low)
        trendlb = vbt.TRENDLB.run(
            high_values,
            low_values,
            config.up_th,
            config.down_th,
            mode=config.mode,
            hide_params=True,
        )
        labels = _binary_from_value_labels(trendlb.labels, config.positive_value)
        return LabelResult(
            labels=labels,
            native_object=trendlb,
            metadata={
                "kind": config.kind,
                "mode": config.mode,
                "up_th": config.up_th,
                "down_th": config.down_th,
                "positive_value": config.positive_value,
                "requires": ["high", "low"],
                "output_shape": table_shape(labels),
            },
        )
    if config.kind == "pivotlb":
        high_values, low_values = _require_high_low(high, low)
        pivotlb = vbt.PIVOTLB.run(
            high_values,
            low_values,
            config.up_th,
            config.down_th,
            hide_params=True,
        )
        labels = _binary_from_value_labels(pivotlb.labels, config.positive_value)
        return LabelResult(
            labels=labels,
            native_object=pivotlb,
            metadata={
                "kind": config.kind,
                "up_th": config.up_th,
                "down_th": config.down_th,
                "positive_value": config.positive_value,
                "requires": ["high", "low"],
                "output_shape": table_shape(labels),
            },
        )
    raise ValueError(f"Unsupported label kind: {config.kind}")


def _binary_from_numeric_labels(
    values: pd.DataFrame, threshold: float
) -> pd.DataFrame:
    labels = (values > threshold).astype("Int8")
    labels = labels.mask(values.isna(), pd.NA)
    return _label_panel(labels)


def _binary_from_value_labels(
    values: pd.DataFrame, positive_value: int
) -> pd.DataFrame:
    labels = (values == positive_value).astype("Int8")
    labels = labels.mask(values.isna(), pd.NA)
    return _label_panel(labels)


def _label_panel(values: Any) -> pd.DataFrame:
    if isinstance(values, pd.Series):
        return values.to_frame(name=values.name or "label")
    return values


def _require_high_low(
    high: pd.DataFrame | None,
    low: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if high is None or low is None:
        raise ValueError("high and low are required for this VectorBT label generator")
    return high, low
