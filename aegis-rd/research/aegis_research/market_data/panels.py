"""Panel mechanics: shaping native source data into per-Array panels.

Lower-level building blocks used by :mod:`features` (the caller-facing
accessors) and the observe pass. Also home to the Result→Bundle builder
so the frozen-type module (:mod:`contracts`) does not depend on panel
mechanics.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from aegis_runtime import MarketDataBundle

from research.aegis_research.market_data.contracts import MarketDataResult


def available_array_panels(
    native_data: Any, requested_arrays: tuple[str, ...]
) -> dict[str, pd.DataFrame]:
    panels = {}
    for name in requested_arrays:
        try:
            panels[name] = canonical_array_panel(native_data, name)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def canonical_array_panel(
    native_data: Any,
    name: str,
) -> pd.DataFrame:
    return array_panel(native_data, name, role=name)


def array_panel(data: Any, name: str, *, role: str) -> pd.DataFrame:
    values = data.get(
        feature=name,
        squeeze_features=False,
        squeeze_symbols=False,
    )
    return as_panel(values, role=role)


def array_from_frame(data: pd.DataFrame, name: str) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if name in data.columns.get_level_values(-1):
            return as_panel(data.xs(name, axis=1, level=-1), role=name)
        if name in data.columns.get_level_values(0):
            return as_panel(data.xs(name, axis=1, level=0), role=name)
    if name in data.columns:
        return as_panel(data[name], role=name)
    raise ValueError(f"Data must contain a {name} column")


def as_panel(values: Any, *, role: str) -> pd.DataFrame:
    if isinstance(values, pd.Series):
        return values.to_frame(name=values.name or role)
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{role} values must be a pandas Series or DataFrame")
    return values


def market_data_bundle(result: MarketDataResult) -> MarketDataBundle:
    """Materialise every declared loaded Array into an eager Bundle."""
    result.assert_usable()
    loaded_arrays = [d.name for d in result.metadata.arrays if d.loaded]
    arrays = {name: canonical_array_panel(result.native_data, name) for name in loaded_arrays}
    return MarketDataBundle(arrays=arrays)
