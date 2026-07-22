"""Observe: a single pass over loaded data producing typed diagnostics.

The one place market data is observed. ``observe_source`` is the load-outcome
entry: a failed load observes nothing and diagnoses every configured
instrument as data-unavailable. ``observe`` shapes the native source
object into a :class:`MarketDataObservation` (index, arrays, instrument IDs, panels);
``diagnose`` turns that observation into the typed per-instrument, per-Array
:class:`DataDiagnostics` records the judge reads. The adapter's index
evidence is observation-level and goes to the judge and the ``provenance``
facet directly; it is not threaded through the per-instrument records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data import panels as _panels
from research.aegis_research.market_data.contracts import (
    QUALITY_DATA_UNAVAILABLE,
    DataArrayDiagnostics,
    DataDiagnostics,
    MarketDataLoad,
)
from research.aegis_research.market_data.identity import as_instrument_id, instrument_ids

_MISSING = object()


@dataclass(frozen=True)
class MarketDataObservation:
    index: pd.Index
    arrays: tuple[str, ...]
    instrument_ids: tuple[InstrumentId, ...]
    panels: dict[str, pd.DataFrame]


def empty_observation() -> MarketDataObservation:
    return MarketDataObservation(index=pd.Index([]), arrays=(), instrument_ids=(), panels={})


def unavailable_diagnostics(config: DataConfig) -> tuple[DataDiagnostics, ...]:
    return tuple(
        DataDiagnostics(
            instrument_id=instrument_id,
            configured=True,
            arrays={},
            load_status=QUALITY_DATA_UNAVAILABLE,
        )
        for instrument_id in _config_instrument_ids(config)
    )


def observe_source(
    config: DataConfig,
    source: MarketDataLoad,
    *,
    requested_arrays: tuple[str, ...],
) -> tuple[MarketDataObservation, tuple[DataDiagnostics, ...]]:
    """Observe one load outcome: a failed load observes nothing and diagnoses
    every configured instrument as data-unavailable; a loaded pull is observed
    and diagnosed."""
    if source.failure is not None:
        return empty_observation(), unavailable_diagnostics(config)
    observation = observe(config, native_data=source.native_data, requested_arrays=requested_arrays)
    return observation, diagnose(config, observation)


def observe(
    config: DataConfig,
    *,
    native_data: Any,
    requested_arrays: tuple[str, ...],
) -> MarketDataObservation:
    index = _optional_attr(native_data, "index")
    features = _optional_attr(native_data, "features")
    native_symbols = _optional_attr(native_data, "symbols")
    values = None
    if index is _MISSING or features is _MISSING or native_symbols is _MISSING:
        values = _native_values(native_data)
    return MarketDataObservation(
        index=_observed_index(index, values),
        arrays=tuple(_observed_arrays(features, values)),
        instrument_ids=tuple(
            _observed_instrument_ids(
                native_symbols,
                values,
                fallback=_config_instrument_ids(config),
            )
        ),
        panels=_observed_array_panels(native_data, requested_arrays, values=values),
    )


def diagnose(
    config: DataConfig,
    observation: MarketDataObservation,
) -> tuple[DataDiagnostics, ...]:
    diagnostics: list[DataDiagnostics] = []
    panels = observation.panels
    configured_instrument_ids = set(_config_instrument_ids(config))
    observed_instrument_ids = set(observation.instrument_ids)
    for instrument_id in observation.instrument_ids:
        diagnostics.append(
            DataDiagnostics(
                instrument_id=instrument_id,
                configured=instrument_id in configured_instrument_ids,
                arrays=_array_diagnostics(
                    panels,
                    instrument_id=instrument_id,
                    arrays=config.effective_arrays,
                ),
                load_status="loaded",
            )
        )
    for instrument_id in _config_instrument_ids(config):
        if instrument_id not in observed_instrument_ids:
            diagnostics.append(
                DataDiagnostics(
                    instrument_id=instrument_id,
                    configured=True,
                    arrays={},
                    load_status="skipped",
                )
            )
    return tuple(diagnostics)


def _array_diagnostics(
    panels: dict[str, pd.DataFrame],
    *,
    instrument_id: InstrumentId,
    arrays: tuple[str, ...],
) -> dict[str, DataArrayDiagnostics]:
    diagnostics: dict[str, DataArrayDiagnostics] = {}
    for name in arrays:
        panel = panels.get(name)
        column = None if panel is None else _column_for_instrument_id(panel, instrument_id)
        if panel is None or column is None:
            diagnostics[name] = DataArrayDiagnostics(available=False)
            continue
        diagnostics[name] = _available_array_diagnostics(panel[column])
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


def _observed_instrument_ids(
    native_symbols: Any,
    values: Any,
    *,
    fallback: tuple[InstrumentId, ...],
) -> list[InstrumentId]:
    if native_symbols is not _MISSING and native_symbols is not None:
        return [_instrument_id(instrument_id) for instrument_id in native_symbols]
    if isinstance(values, pd.DataFrame) and isinstance(values.columns, pd.MultiIndex):
        level = "symbol" if "symbol" in values.columns.names else 0
        return sorted(
            {
                _instrument_id(instrument_id)
                for instrument_id in values.columns.get_level_values(level)
            },
            key=lambda instrument_id: instrument_id.value,
        )
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


def _column_for_instrument_id(panel: pd.DataFrame, instrument_id: InstrumentId) -> Any | None:
    for column in panel.columns:
        if _instrument_id(column) == instrument_id:
            return column
    return None


def _config_instrument_ids(config: DataConfig) -> tuple[InstrumentId, ...]:
    return instrument_ids(config.instruments)


def _instrument_id(value: Any) -> InstrumentId:
    return as_instrument_id(value)
