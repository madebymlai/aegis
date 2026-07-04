from __future__ import annotations

from typing import Any

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration import OHLCV_ARRAYS, DataConfig
from research.aegis_research.market_data.contracts import (
    ArrayDescriptor,
    CoverageFacet,
    DataDiagnostics,
    MarketDataAdapterResult,
    MarketDataMetadataV3,
    MarketDataQuality,
    ProvenanceFacet,
    RequestFacet,
)
from research.aegis_research.market_data.diagnostics import MarketDataObservation
from research.aegis_research.market_data.identity import instrument_ids

__all__ = ["MarketDataObservation", "describe"]


def describe(
    config: DataConfig,
    *,
    source: MarketDataAdapterResult,
    observation: MarketDataObservation,
    diagnostics: tuple[DataDiagnostics, ...],
    quality: MarketDataQuality,
    required_arrays: tuple[str, ...],
) -> MarketDataMetadataV3:
    """Assemble the schema-versioned ``market_data.v3`` typed metadata model.

    The single authority for the metadata wire contract.  Facet-shaped
    (ADR-0020): one ``arrays`` descriptor list replaces eight parallel
    Array-name lists; duplicate, derivable, and vestigial keys are dropped.

    The provenance facet is projected whole from the pull outcome
    (``source``): provider internals come scrubbed off the adapter result,
    and a failed pull's source metadata (error type and summary) is derived
    here — the wire shape of failure is this module's knowledge, not the
    loader's.  A failed pull keeps the same facet keys as the success shape,
    with the provider internals collapsed to their empty values.
    """
    index = observation.index
    observed_arrays = list(observation.arrays)
    observed_instrument_ids = list(observation.instrument_ids)
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
            requested_instrument_ids=list(instrument_ids(config.instruments)),
            timeframe=config.timeframe,
            authored_arrays=to_builtin(config.arrays),
            effective_arrays=list(config.effective_arrays),
        ),
        arrays=array_descriptors,
        coverage=CoverageFacet(
            instrument_ids=observed_instrument_ids,
            rows=len(index),
            start=str(index[0]) if len(index) else None,
            end=str(index[-1]) if len(index) else None,
        ),
        quality=quality,
        diagnostics=list(diagnostics),
        provenance=ProvenanceFacet(
            provider_class=source.provider_class,
            source_metadata=_source_metadata(source, quality),
            index_evidence=source.evidence,
            provider_metadata=source.provider_metadata,
            omitted_metadata_fields=source.omitted_metadata_fields,
            update_supported=source.update_supported,
            missing_index=config.missing_index,
            missing_columns=config.missing_columns,
            tz_localize=config.tz_localize,
            tz_convert=config.tz_convert,
            skip_on_error=config.skip_on_error,
            silence_warnings=config.silence_warnings,
        ),
    )


def _source_metadata(
    source: MarketDataAdapterResult, quality: MarketDataQuality
) -> dict[str, Any]:
    if source.failure is None:
        return source.source_metadata
    return {
        "provider_error_type": type(source.failure).__name__,
        "provider_error_summary": quality.reasons[0] if quality.reasons else quality.state,
    }
