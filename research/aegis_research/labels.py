from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import LabelConfig
from research.aegis_research.data_schema import primary_series, table_shape


@dataclass(frozen=True)
class LabelResult:
    labels: pd.Series
    metadata: dict[str, Any]
    native_object: Any | None = None


def build_labels(
    close: pd.Series | pd.DataFrame,
    config: LabelConfig,
    high: pd.Series | pd.DataFrame | None = None,
    low: pd.Series | pd.DataFrame | None = None,
) -> pd.Series:
    return build_label_result(close, config, high=high, low=low).labels


def build_label_result(
    close: pd.Series | pd.DataFrame,
    config: LabelConfig,
    high: pd.Series | pd.DataFrame | None = None,
    low: pd.Series | pd.DataFrame | None = None,
) -> LabelResult:
    close_series = primary_series(close, role="close")
    if config.kind == "fixlb":
        fixlb = vbt.FIXLB.run(close_series, n=config.horizon, hide_params=True)
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
        high_series, low_series = _require_high_low(high, low)
        trendlb = vbt.TRENDLB.run(
            primary_series(high_series, role="high"),
            primary_series(low_series, role="low"),
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
        high_series, low_series = _require_high_low(high, low)
        pivotlb = vbt.PIVOTLB.run(
            primary_series(high_series, role="high"),
            primary_series(low_series, role="low"),
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


def _binary_from_numeric_labels(values: pd.Series, threshold: float) -> pd.Series:
    labels = (values > threshold).astype("Int8")
    labels[values.isna()] = pd.NA
    return labels.rename("label")


def _binary_from_value_labels(values: pd.Series, positive_value: int) -> pd.Series:
    labels = (values == positive_value).astype("Int8")
    labels[values.isna()] = pd.NA
    return labels.rename("label")


def _require_high_low(
    high: pd.Series | pd.DataFrame | None,
    low: pd.Series | pd.DataFrame | None,
) -> tuple[pd.Series | pd.DataFrame, pd.Series | pd.DataFrame]:
    if high is None or low is None:
        raise ValueError("high and low are required for this VectorBT label generator")
    return high, low
