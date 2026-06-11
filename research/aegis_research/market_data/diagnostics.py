"""Observe: a single pass over loaded data producing typed diagnostics.

The one place market data is observed. ``observe`` shapes the native source
object into a :class:`MarketDataObservation` (index, arrays, symbols, panels);
``diagnose`` turns that observation plus the adapter's index evidence into the
typed per-symbol, per-Array :class:`DataDiagnostics` records the judge reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data import panels as _panels
from research.aegis_research.market_data.contracts import (
    QUALITY_PROVIDER_FAILED,
    DataArrayDiagnostics,
    DataDiagnostics,
)

_MISSING = object()


@dataclass(frozen=True)
class MarketDataObservation:
    index: pd.Index
    arrays: tuple[str, ...]
    symbols: tuple[str, ...]
    panels: dict[str, pd.DataFrame]


def empty_observation() -> MarketDataObservation:
    return MarketDataObservation(index=pd.Index([]), arrays=(), symbols=(), panels={})


def provider_failed_diagnostics(config: DataConfig) -> tuple[DataDiagnostics, ...]:
    return tuple(
        DataDiagnostics(
            symbol=symbol,
            configured=True,
            arrays={},
            index_evidence={"source": "provider_failed"},
            provider_status=QUALITY_PROVIDER_FAILED,
        )
        for symbol in config.symbols
    )


def observe(
    config: DataConfig,
    *,
    native_data: Any,
    requested_arrays: tuple[str, ...],
) -> MarketDataObservation:
    index = _optional_attr(native_data, "index")
    features = _optional_attr(native_data, "features")
    symbols = _optional_attr(native_data, "symbols")
    values = None
    if index is _MISSING or features is _MISSING or symbols is _MISSING:
        values = _native_values(native_data)
    return MarketDataObservation(
        index=_observed_index(index, values),
        arrays=tuple(_observed_arrays(features, values)),
        symbols=tuple(_observed_symbols(symbols, values, fallback=config.symbols)),
        panels=_observed_array_panels(native_data, requested_arrays, values=values),
    )


def diagnose(
    config: DataConfig,
    observation: MarketDataObservation,
    *,
    evidence: dict[str, Any],
) -> tuple[DataDiagnostics, ...]:
    diagnostics: list[DataDiagnostics] = []
    panels = observation.panels
    observed_symbols = set(observation.symbols)
    for symbol in observation.symbols:
        diagnostics.append(
            DataDiagnostics(
                symbol=str(symbol),
                configured=symbol in config.symbols,
                arrays=_array_diagnostics(
                    panels,
                    symbol=symbol,
                    arrays=config.effective_arrays,
                ),
                index_evidence=evidence,
                provider_status="loaded",
            )
        )
    for symbol in config.symbols:
        if symbol not in observed_symbols:
            diagnostics.append(
                DataDiagnostics(
                    symbol=symbol,
                    configured=True,
                    arrays={},
                    index_evidence=evidence,
                    provider_status="skipped",
                )
            )
    return tuple(diagnostics)


def _array_diagnostics(
    panels: dict[str, pd.DataFrame],
    *,
    symbol: str,
    arrays: tuple[str, ...],
) -> dict[str, DataArrayDiagnostics]:
    diagnostics: dict[str, DataArrayDiagnostics] = {}
    for name in arrays:
        panel = panels.get(name)
        if panel is None or symbol not in panel.columns:
            diagnostics[name] = DataArrayDiagnostics(available=False)
            continue
        diagnostics[name] = _available_array_diagnostics(panel[symbol])
    return diagnostics


def _available_array_diagnostics(series: pd.Series) -> DataArrayDiagnostics:
    missing_count = int(series.isna().sum())
    row_count = len(series)
    return DataArrayDiagnostics(
        available=True,
        rows=row_count,
        missing=missing_count,
        coverage=(row_count - missing_count) / row_count if row_count else 0,
        numeric=bool(pd.api.types.is_numeric_dtype(series)),
        first_timestamp=str(series.index[0]) if row_count else None,
        last_timestamp=str(series.index[-1]) if row_count else None,
    )


def _optional_attr(native_data: Any, name: str) -> Any:
    try:
        return getattr(native_data, name)
    except AttributeError:
        return _MISSING


def _native_values(native_data: Any) -> Any:
    if isinstance(native_data, pd.DataFrame | pd.Series):
        return native_data
    getter = getattr(native_data, "get", None)
    if callable(getter):
        return getter()
    return None


def _observed_index(index: Any, values: Any) -> pd.Index:
    if index is not _MISSING:
        return index
    if isinstance(values, (pd.Series, pd.DataFrame)):
        return values.index
    return pd.Index([])


def _observed_arrays(features: Any, values: Any) -> list[str]:
    if features is not _MISSING and features is not None:
        return list(map(str, features))
    if isinstance(values, pd.DataFrame):
        return _frame_arrays(values)
    return []


def _observed_symbols(symbols: Any, values: Any, *, fallback: list[str]) -> list[str]:
    if symbols is not _MISSING and symbols is not None:
        return list(map(str, symbols))
    if isinstance(values, pd.DataFrame) and isinstance(values.columns, pd.MultiIndex):
        level = "symbol" if "symbol" in values.columns.names else 0
        return sorted(set(map(str, values.columns.get_level_values(level))))
    return list(fallback)


def _observed_array_panels(
    native_data: Any,
    requested_arrays: tuple[str, ...],
    *,
    values: Any,
) -> dict[str, pd.DataFrame]:
    if isinstance(values, pd.DataFrame):
        return _frame_array_panels(values, requested_arrays)
    if isinstance(values, pd.Series):
        return _series_array_panels(values, requested_arrays)
    return _panels.available_array_panels(native_data, requested_arrays)


def _frame_array_panels(
    values: pd.DataFrame,
    requested_arrays: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    panels = {}
    for name in requested_arrays:
        try:
            panels[name] = _panels.array_from_frame(values, name)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def _series_array_panels(
    values: pd.Series,
    requested_arrays: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    if str(values.name) not in requested_arrays:
        return {}
    return {str(values.name): _panels.as_panel(values, role=str(values.name))}


def _frame_arrays(frame: pd.DataFrame) -> list[str]:
    if isinstance(frame.columns, pd.MultiIndex):
        values = frame.columns.get_level_values(
            "feature" if "feature" in frame.columns.names else -1
        )
        return sorted(set(map(str, values)))
    return list(map(str, frame.columns))
