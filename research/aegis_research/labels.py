from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import LabelConfig


def build_labels(
    close: pd.Series | pd.DataFrame,
    config: LabelConfig,
    high: pd.Series | pd.DataFrame | None = None,
    low: pd.Series | pd.DataFrame | None = None,
) -> pd.Series:
    close_series = _primary_close(close)
    if config.kind == "fixlb":
        fixlb = vbt.FIXLB.run(close_series, n=config.horizon, hide_params=True)
        return _binary_from_numeric_labels(fixlb.labels, config.threshold)
    if config.kind == "trendlb":
        high_series, low_series = _require_high_low(high, low)
        trendlb = vbt.TRENDLB.run(
            _primary_close(high_series),
            _primary_close(low_series),
            config.up_th,
            config.down_th,
            mode=config.mode,
            hide_params=True,
        )
        return _binary_from_value_labels(trendlb.labels, config.positive_value)
    if config.kind == "pivotlb":
        high_series, low_series = _require_high_low(high, low)
        pivotlb = vbt.PIVOTLB.run(
            _primary_close(high_series),
            _primary_close(low_series),
            config.up_th,
            config.down_th,
            hide_params=True,
        )
        return _binary_from_value_labels(pivotlb.labels, config.positive_value)
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


def _primary_close(close: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(close, pd.Series):
        return close
    return close.iloc[:, 0].rename(str(close.columns[0]))
