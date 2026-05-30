from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import DataConfig
from research.aegis_research.configuration.secrets import to_builtin
from research.aegis_research.market_data import safety as _safety
from research.aegis_research.market_data.contracts import (
    OHLCV_FEATURES,
    DataDiagnostics,
    MarketDataQuality,
)


@dataclass(frozen=True)
class MarketDataObservation:
    index: pd.Index
    features: tuple[str, ...]
    symbols: tuple[str, ...]
    panels: dict[str, pd.DataFrame]


def describe(
    config: DataConfig,
    *,
    native_data: Any,
    observation: MarketDataObservation,
    diagnostics: tuple[DataDiagnostics, ...],
    quality: MarketDataQuality,
    source_metadata: dict[str, Any],
    evidence: dict[str, Any],
    required_features: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble the schema-versioned ``market_data.v2`` public metadata dict.

    The single authority for the metadata wire contract. Tolerates
    ``native_data is None`` (the provider-failure path), in which case the
    provider/native classes and provider metadata collapse to their empty
    shapes while the dict keeps the same keys as the success shape.
    """
    index = observation.index
    features = list(observation.features)
    symbols = list(observation.symbols)
    panels = observation.panels
    provider_metadata, omitted = _provider_metadata(native_data, source=config.source)
    metadata: dict[str, Any] = {
        "schema_version": "market_data.v2",
        "source": config.source,
        "provider_class": _native_class_name(native_data),
        "native_class": _native_class_name(native_data),
        "requested_symbols": list(config.symbols),
        "symbols": symbols,
        "features": features,
        "canonical_features": list(panels),
        "authored_arrays": to_builtin(config.arrays),
        "effective_arrays": list(config.effective_arrays),
        "required_arrays": list(required_features),
        "loaded_arrays": list(panels),
        "unavailable_arrays": [feature for feature in required_features if feature not in panels],
        "timeframe": config.timeframe,
        "shape": {
            "rows": len(index),
            "symbols": len(symbols),
            "features": len(features),
            "columns": len(symbols) * len(features),
        },
        "ohlc_available": {feature: feature in panels for feature in OHLCV_FEATURES},
        "index_start": str(index[0]) if len(index) else None,
        "index_end": str(index[-1]) if len(index) else None,
        "missing_index": config.missing_index,
        "missing_columns": config.missing_columns,
        "tz_localize": config.tz_localize,
        "tz_convert": config.tz_convert,
        "skip_on_error": config.skip_on_error,
        "silence_warnings": config.silence_warnings,
        "quality": quality.to_metadata(),
        "diagnostics": _diagnostics_metadata(diagnostics),
        "source_metadata": source_metadata,
        "index_evidence": evidence,
        "provider_metadata": provider_metadata,
        "omitted_metadata_fields": omitted,
        "update_supported": _supports_update(native_data),
        "cache_policy": "disabled_in_schema_v2",
    }
    return to_builtin(metadata)


def _native_class_name(native_data: Any) -> str | None:
    if native_data is None:
        return None
    return type(native_data).__name__


def _supports_update(native_data: Any) -> bool:
    if native_data is None:
        return False
    return _safety.supports_update(native_data)


def _provider_metadata(
    native_data: Any, *, source: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if native_data is None:
        return {}, []
    projected = _safety.safe_native_data_metadata(native_data, source=source)
    return projected["metadata"], projected["omitted"]


def _diagnostics_metadata(diagnostics: tuple[DataDiagnostics, ...]) -> list[dict[str, Any]]:
    return [diagnostic.to_metadata() for diagnostic in diagnostics]
