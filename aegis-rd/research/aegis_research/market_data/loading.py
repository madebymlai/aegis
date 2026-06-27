"""Orchestrator: wire observe -> judge -> describe behind the adapter seam.

`loading` owns no concern logic. It dispatches to a source adapter, then
threads the result through the leaf modules — observe (:mod:`diagnostics`),
judge (:mod:`quality`), describe (:mod:`metadata`). Public feature accessors
are re-exported from :mod:`features` so the facade surface stays stable.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration import DataConfig, merge_data_arrays
from research.aegis_research.market_data import diagnostics as _observe
from research.aegis_research.market_data import features as _features
from research.aegis_research.market_data import metadata as _metadata
from research.aegis_research.market_data import native_metadata as _native_metadata
from research.aegis_research.market_data import quality as _judge
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import (
    MarketDataAdapter,
    MarketDataResult,
    RemoteDataPullError,
)

close_from_ohlcv = _features.close_from_ohlcv
array_from_ohlcv = _features.array_from_ohlcv
high_from_ohlcv = _features.high_from_ohlcv
low_from_ohlcv = _features.low_from_ohlcv
required_ohlcv_arrays = _features.required_ohlcv_arrays
required_experiment_ohlcv_arrays = _features.required_experiment_ohlcv_arrays

MarketDataObservation = _observe.MarketDataObservation

__all__ = [
    "array_from_ohlcv",
    "close_from_ohlcv",
    "high_from_ohlcv",
    "load_market_data",
    "load_market_data_result",
    "low_from_ohlcv",
    "required_experiment_ohlcv_arrays",
    "required_ohlcv_arrays",
]


def load_market_data(config: DataConfig) -> Any:
    result = load_market_data_result(config)
    result.assert_usable()
    return result.native_data


def load_market_data_result(
    config: DataConfig,
    *,
    required_arrays: tuple[str, ...] | None = None,
    adapter: MarketDataAdapter | None = None,
) -> MarketDataResult:
    """Load catalog data, then apply Aegis evidence/quality contracts."""
    requested = config.effective_arrays
    required = merge_data_arrays(requested, required_arrays or ())
    load_data = load_catalog_source if adapter is None else adapter

    try:
        adapter_result = load_data(config)
    except RemoteDataPullError as error:
        return _provider_failed_result(config, error, required_arrays=required)

    native_data = adapter_result.native_data
    observation = _observe.observe(
        config, native_data=native_data, requested_arrays=requested
    )
    diagnostics = _observe.diagnose(config, observation)
    quality = _judge.evaluate(
        config,
        diagnostics,
        required_arrays=required,
        index_evidence=adapter_result.evidence,
    )
    metadata = _metadata.describe(
        config,
        native_class=_native_class(native_data),
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        source_metadata=adapter_result.source_metadata,
        evidence=adapter_result.evidence,
        provider_metadata=adapter_result.provider_metadata,
        omitted_metadata_fields=adapter_result.omitted_metadata_fields,
        update_supported=_update_supported(native_data),
        required_arrays=required,
    )
    return MarketDataResult(
        native_data=native_data,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
        pnl_native_data=adapter_result.pnl_native_data,
        currency_conversion=adapter_result.currency_conversion,
    )


def _provider_failed_result(
    config: DataConfig,
    error: RemoteDataPullError,
    *,
    required_arrays: tuple[str, ...],
) -> MarketDataResult:
    diagnostics = _observe.provider_failed_diagnostics(config)
    quality = _judge.evaluate(
        config,
        diagnostics,
        required_arrays=required_arrays,
        index_evidence={"source": "provider_failed"},
    )
    reason = quality.reasons[0] if quality.reasons else quality.state
    metadata = _metadata.describe(
        config,
        native_class=None,
        observation=_observe.empty_observation(),
        diagnostics=diagnostics,
        quality=quality,
        source_metadata={
            "provider_error_type": type(error).__name__,
            "provider_error_summary": reason,
        },
        evidence={"source": "provider_failed"},
        provider_metadata={},
        omitted_metadata_fields=[],
        update_supported=False,
        required_arrays=required_arrays,
    )
    return MarketDataResult(
        native_data=None,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
    )


def _native_class(native_data: Any) -> str | None:
    if native_data is None:
        return None
    return type(native_data).__name__


def _update_supported(native_data: Any) -> bool:
    if native_data is None:
        return False
    return _native_metadata.supports_update(native_data)
