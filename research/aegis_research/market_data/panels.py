"""Panel mechanics: shaping native source data into per-feature panels.

Lower-level building blocks used by :mod:`features` (the caller-facing
accessors) and the observe pass. Also home to the Result→Bundle builder
so the frozen-type module (:mod:`contracts`) does not depend on panel
mechanics.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.market_data.contracts import (
    MarketDataBundle,
    MarketDataResult,
)


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


def market_data_bundle(result: MarketDataResult) -> MarketDataBundle:
    """Materialise every declared loaded Array into an eager Bundle."""
    result.assert_usable()
    loaded_arrays = result.metadata.get("loaded_arrays", ())
    features = {
        name: canonical_feature_panel(result.native_data, name)
        for name in loaded_arrays
    }
    return MarketDataBundle(features=features)
