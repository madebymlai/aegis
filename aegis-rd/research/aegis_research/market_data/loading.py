"""Orchestrator: wire observe -> judge -> describe behind the adapter seam.

`loading` owns no concern logic. It dispatches to a source adapter — a failed
pull collapses to the degenerate adapter result, so failure rides the same
sequence as success — then threads the outcome through the leaf modules:
observe (:mod:`diagnostics`), judge (:mod:`quality`), describe
(:mod:`metadata`). Public feature accessors are re-exported from
:mod:`features` so the facade surface stays stable.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.configuration import DataConfig, merge_data_arrays
from research.aegis_research.market_data import diagnostics as _observe
from research.aegis_research.market_data import features as _features
from research.aegis_research.market_data import metadata as _metadata
from research.aegis_research.market_data import quality as _judge
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import (
    MarketDataAdapter,
    MarketDataResult,
    RemoteDataPullError,
    provider_failed_adapter_result,
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
        source = load_data(config)
    except RemoteDataPullError as error:
        source = provider_failed_adapter_result(error)

    observation, diagnostics = _observe.observe_source(
        config, source, requested_arrays=requested
    )
    quality = _judge.evaluate(
        config,
        diagnostics,
        required_arrays=required,
        index_evidence=source.evidence,
    )
    metadata = _metadata.describe(
        config,
        source=source,
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        required_arrays=required,
    )
    return MarketDataResult(
        native_data=source.native_data,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
        pnl_native_data=source.pnl_native_data,
        currency_conversion=source.currency_conversion,
        adjustment_mode=source.adjustment_mode,
        distributions=source.distributions,
    )
