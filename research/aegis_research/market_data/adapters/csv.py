from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import (
    DataConfig,
    has_data_array_token_shape,
)
from research.aegis_research.data_arrays import merge_data_arrays
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_feature_data,
    safe_provider_metadata,
)
from research.aegis_research.market_data.contracts import MarketDataAdapterResult


def load_csv_source(config: DataConfig) -> MarketDataAdapterResult:
    if config.path is None:
        raise ValueError("data.path is required for csv source")
    frame = _read_csv(config)
    evidence = index_evidence(frame.index, source="csv_raw")
    feature_data = _csv_feature_data(frame, config)
    native_data = native_from_feature_data(feature_data, config)
    projected = safe_provider_metadata(native_data, source=config.source)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"path": "<redacted>", "layout": _csv_layout(frame)},
        evidence=evidence,
        provider_metadata=projected["metadata"],
        omitted_metadata_fields=projected["omitted"],
    )


def _read_csv(config: DataConfig) -> pd.DataFrame:
    path = Path(config.path or "")
    if _csv_looks_multiindex(path, config):
        return _localize_csv_index(pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True))
    return _localize_csv_index(pd.read_csv(path, index_col=0, parse_dates=True))


def _csv_looks_multiindex(path: Path, config: DataConfig) -> bool:
    rows = _csv_probe_rows(path, limit=2)
    if len(rows) < 2:
        return False
    first_header = set(map(str, rows[0][1:]))
    if first_header & set(config.effective_arrays):
        return False
    second_header = rows[1][1:]
    second_values = set(map(str, second_header))
    multiindex_markers = set(config.symbols) | set(config.effective_arrays)
    return (
        bool(second_header)
        and bool((first_header | second_values) & multiindex_markers)
        and not any(str(value).startswith("Unnamed") for value in second_header)
    )


def _csv_probe_rows(path: Path, *, limit: int) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(row)
            if len(rows) == limit:
                break
    return rows


def _localize_csv_index(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def _csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if isinstance(frame.columns, pd.MultiIndex):
        return _multiindex_csv_feature_data(frame, config)
    return _flat_csv_feature_data(frame, config)


def _flat_csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if len(config.symbols) != 1:
        raise ValueError("flat CSV feature input requires exactly one configured symbol")
    symbol = config.symbols[0]
    feature_data: dict[str, pd.DataFrame] = {}
    for feature in _csv_feature_candidates(map(str, frame.columns), config):
        if feature in frame.columns:
            panel = frame.loc[:, [feature]].copy()
            panel.columns = pd.Index([symbol] * len(panel.columns), name=frame.columns.name)
            feature_data[feature] = panel
    if not feature_data:
        raise ValueError("CSV data must contain at least one requested VBT feature column")
    return feature_data


def _multiindex_csv_feature_data(
    frame: pd.DataFrame, config: DataConfig
) -> dict[str, pd.DataFrame]:
    symbol_level, feature_level = _csv_multiindex_levels(frame, config)
    feature_data = {}
    feature_values = set(map(str, frame.columns.get_level_values(feature_level)))
    for feature in _csv_feature_candidates(frame.columns.get_level_values(feature_level), config):
        if feature not in feature_values:
            continue
        panel = frame.xs(feature, axis=1, level=feature_level)
        if isinstance(panel.columns, pd.MultiIndex):
            panel.columns = panel.columns.get_level_values(symbol_level)
        panel = panel.loc[:, [symbol for symbol in config.symbols if symbol in panel.columns]]
        if not panel.empty:
            feature_data[feature] = panel
    if not feature_data:
        raise ValueError("CSV MultiIndex data must contain at least one requested VBT feature")
    return feature_data


def _csv_multiindex_levels(frame: pd.DataFrame, config: DataConfig) -> tuple[int, int]:
    level_values = [
        set(map(str, frame.columns.get_level_values(index)))
        for index in range(frame.columns.nlevels)
    ]
    configured_symbols = set(config.symbols)
    symbol_levels = [
        index for index, values in enumerate(level_values) if configured_symbols & values
    ]
    source_features = set(config.effective_arrays)
    source_features.update(
        value
        for values in level_values
        for value in values
        if value not in configured_symbols and _looks_like_vbt_feature_name(value)
    )
    feature_levels = [
        index for index, values in enumerate(level_values) if source_features & values
    ]
    if not symbol_levels or not feature_levels:
        raise ValueError("CSV MultiIndex columns must include symbol and feature levels")
    symbol_level = symbol_levels[0]
    feature_level = next(
        (level for level in feature_levels if level != symbol_level), feature_levels[0]
    )
    if symbol_level == feature_level:
        raise ValueError("CSV MultiIndex symbol and feature levels must be distinct")
    return symbol_level, feature_level


def _csv_feature_candidates(values: Any, config: DataConfig) -> tuple[str, ...]:
    candidates = tuple(
        value
        for value in dict.fromkeys(map(str, values))
        if value not in config.symbols and _looks_like_vbt_feature_name(value)
    )
    return merge_data_arrays(config.effective_arrays, candidates)


def _looks_like_vbt_feature_name(value: str) -> bool:
    return has_data_array_token_shape(value)


def _csv_layout(frame: pd.DataFrame) -> str:
    return "multiindex" if isinstance(frame.columns, pd.MultiIndex) else "flat"
