from __future__ import annotations

from typing import Any

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration import DataConfig, OHLCV_ARRAYS
from research.aegis_research.market_data.contracts import (
    DataDiagnostics,
    MarketDataQuality,
)
from research.aegis_research.market_data.diagnostics import MarketDataObservation

__all__ = ["MarketDataObservation", "describe"]


def describe(
    config: DataConfig,
    *,
    native_class: str | None,
    observation: MarketDataObservation,
    diagnostics: tuple[DataDiagnostics, ...],
    quality: MarketDataQuality,
    source_metadata: dict[str, Any],
    evidence: dict[str, Any],
    provider_metadata: dict[str, Any],
    omitted_metadata_fields: list[dict[str, str]],
    update_supported: bool,
    required_arrays: tuple[str, ...],
) -> dict[str, Any]:
    """Assemble the schema-versioned ``market_data.v2`` public metadata dict.

    The single authority for the metadata wire contract. The provider internals
    (``provider_metadata``, ``omitted_metadata_fields``, ``update_supported``,
    ``native_class``) are scrubbed and supplied by the source adapter; describe
    never reaches into the native object. Tolerates the provider-failure path,
    where those inputs collapse to their empty shapes while the dict keeps the
    same keys as the success shape.
    """
    index = observation.index
    observed_arrays = list(observation.arrays)
    symbols = list(observation.symbols)
    panels = observation.panels
    metadata: dict[str, Any] = {
        "schema_version": "market_data.v2",
        "source": config.source,
        "provider_class": native_class,
        "native_class": native_class,
        "requested_symbols": list(config.symbols),
        "symbols": symbols,
        "features": observed_arrays,
        "canonical_features": list(panels),
        "authored_arrays": to_builtin(config.arrays),
        "effective_arrays": list(config.effective_arrays),
        "required_arrays": list(required_arrays),
        "loaded_arrays": list(panels),
        "unavailable_arrays": [name for name in required_arrays if name not in panels],
        "timeframe": config.timeframe,
        "shape": {
            "rows": len(index),
            "symbols": len(symbols),
            "features": len(observed_arrays),
            "columns": len(symbols) * len(observed_arrays),
        },
        "ohlc_available": {name: name in panels for name in OHLCV_ARRAYS},
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
        "omitted_metadata_fields": omitted_metadata_fields,
        "update_supported": update_supported,
        "cache_policy": "disabled_in_schema_v2",
    }
    return to_builtin(metadata)


def _diagnostics_metadata(diagnostics: tuple[DataDiagnostics, ...]) -> list[dict[str, Any]]:
    return [diagnostic.to_metadata() for diagnostic in diagnostics]
