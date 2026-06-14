from __future__ import annotations

from typing import Any

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration import OHLCV_ARRAYS, DataConfig
from research.aegis_research.market_data.contracts import (
    ArrayDescriptor,
    CoverageFacet,
    DataDiagnostics,
    MarketDataMetadataV3,
    MarketDataQuality,
    ProvenanceFacet,
    RequestFacet,
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
) -> MarketDataMetadataV3:
    """Assemble the schema-versioned ``market_data.v3`` typed metadata model.

    The single authority for the metadata wire contract.  Facet-shaped
    (ADR-0020): one ``arrays`` descriptor list replaces eight parallel
    Array-name lists; duplicate, derivable, and vestigial keys are dropped.

    The provider internals (``provider_metadata``, ``omitted_metadata_fields``,
    ``update_supported``, ``native_class``) are scrubbed and supplied by the
    source adapter; describe never reaches into the native object.  Tolerates
    the provider-failure path, where those inputs collapse to their empty
    shapes while the model keeps the same facet keys as the success shape.
    """
    index = observation.index
    observed_arrays = list(observation.arrays)
    symbols = list(observation.symbols)
    panels = observation.panels
    ohlc_arrays = OHLCV_ARRAYS
    all_requested_names: set[str] = set(required_arrays) | set(observed_arrays)
    array_descriptors = [
        ArrayDescriptor(
            name=name,
            required=name in required_arrays,
            loaded=name in panels,
            observed=name in observed_arrays,
            ohlc=name in ohlc_arrays,
        )
        for name in sorted(all_requested_names)
    ]
    return MarketDataMetadataV3(
        schema_version="market_data.v3",
        request=RequestFacet(
            source=config.source,
            requested_symbols=list(config.tickers),
            timeframe=config.timeframe,
            authored_arrays=to_builtin(config.arrays),
            effective_arrays=list(config.effective_arrays),
        ),
        arrays=array_descriptors,
        coverage=CoverageFacet(
            symbols=symbols,
            rows=len(index),
            start=str(index[0]) if len(index) else None,
            end=str(index[-1]) if len(index) else None,
        ),
        quality=quality,
        diagnostics=list(diagnostics),
        provenance=ProvenanceFacet(
            provider_class=native_class,
            source_metadata=source_metadata,
            index_evidence=evidence,
            provider_metadata=provider_metadata,
            omitted_metadata_fields=omitted_metadata_fields,
            update_supported=update_supported,
            missing_index=config.missing_index,
            missing_columns=config.missing_columns,
            tz_localize=config.tz_localize,
            tz_convert=config.tz_convert,
            skip_on_error=config.skip_on_error,
            silence_warnings=config.silence_warnings,
        ),
    )
