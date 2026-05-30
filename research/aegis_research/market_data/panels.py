from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.market_data.contracts import MarketDataResult


def close_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Close")


def high_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "High")


def low_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Low")


def feature_from_ohlcv(data: Any, feature: str) -> pd.DataFrame:
    if isinstance(data, MarketDataResult):
        data.assert_usable()
        loaded = tuple(data.metadata.get("loaded_arrays", ()))
        if loaded and feature not in loaded:
            raise ValueError(f"market data feature {feature!r} was not loaded for this run")
        return canonical_feature_panel(data.native_data, feature)
    if hasattr(data, "get") and not isinstance(data, pd.DataFrame):
        return feature_panel(data, feature, role=feature)
    return feature_from_frame(data, feature)


def available_feature_panels(
    native_data: Any, requested_features: tuple[str, ...]
) -> dict[str, pd.DataFrame]:
    panels = {}
    for feature in requested_features:
        try:
            panels[feature] = canonical_feature_panel(native_data, feature)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def canonical_feature_panel(
    native_data: Any,
    feature: str,
) -> pd.DataFrame:
    return feature_panel(native_data, feature, role=feature)


def feature_panel(data: Any, feature: str, *, role: str) -> pd.DataFrame:
    values = data.get(
        feature=feature,
        squeeze_features=False,
        squeeze_symbols=False,
    )
    return as_panel(values, role=role)


def feature_from_frame(data: pd.DataFrame, feature: str) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if feature in data.columns.get_level_values(-1):
            return as_panel(data.xs(feature, axis=1, level=-1), role=feature)
        if feature in data.columns.get_level_values(0):
            return as_panel(data.xs(feature, axis=1, level=0), role=feature)
    if feature in data.columns:
        return as_panel(data[feature], role=feature)
    raise ValueError(f"Data must contain a {feature} column")


def as_panel(values: Any, *, role: str) -> pd.DataFrame:
    if isinstance(values, pd.Series):
        return values.to_frame(name=values.name or role)
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{role} values must be a pandas Series or DataFrame")
    return values
