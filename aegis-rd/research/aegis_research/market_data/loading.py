"""Orchestrator: wire observe -> judge -> describe over the catalog loader.

`loading` owns no concern logic. It loads through the catalog loader — the
one implementation, behind the ``CatalogBackedDataPort`` seam — and an
unavailable window collapses to the degenerate load, so failure rides the
same sequence as success. The outcome threads through the leaf modules:
observe (:mod:`diagnostics`), judge (:mod:`quality`), describe
(:mod:`metadata`). Public feature accessors are re-exported from
:mod:`features` so the facade surface stays stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from research.aegis_research.configuration import DataConfig, merge_data_arrays
from research.aegis_research.market_data import diagnostics as _observe
from research.aegis_research.market_data import features as _features
from research.aegis_research.market_data import metadata as _metadata
from research.aegis_research.market_data import quality as _judge
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import (
    MarketDataLoad,
    MarketDataResult,
    MarketDataUnavailableError,
    failed_market_data_load,
)

if TYPE_CHECKING:
    from aegis_data.catalog import CatalogBackedDataPort

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


def load_market_data(
    config: DataConfig, *, port: CatalogBackedDataPort | None = None
) -> Any:
    result = load_market_data_result(config, port=port)
    result.assert_usable()
    return result.native_data


def load_market_data_result(
    config: DataConfig,
    *,
    required_arrays: tuple[str, ...] | None = None,
    port: CatalogBackedDataPort | None = None,
) -> MarketDataResult:
    """Load catalog data, then apply Aegis evidence/quality contracts.

    ``port`` is the one injection seam — the same ``CatalogBackedDataPort``
    production wires — threaded to the catalog loader; omitted, the standard
    port is composed inside aegis-data.
    """
    try:
        source = load_catalog_source(config, port=port)
    except MarketDataUnavailableError as error:
        # The failure rides the same observe -> judge -> describe sequence as
        # success, so an unavailable window becomes judged Run Evidence.
        source = failed_market_data_load(error)
    return result_from_load(config, source, required_arrays=required_arrays)


def result_from_load(
    config: DataConfig,
    source: MarketDataLoad,
    *,
    required_arrays: tuple[str, ...] | None = None,
) -> MarketDataResult:
    """Assemble a :class:`MarketDataResult` from one load outcome — the fixed
    observe → judge → describe sequence (ADR-0005), owned here once.

    Internal seam, not part of the facade: leaf-altitude tests cross it with
    hand-built loads (shapes the catalog loader cannot emit) so the sequence
    can never drift between production and test support.
    """
    requested = config.effective_arrays
    required = merge_data_arrays(requested, required_arrays or ())
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
        size_increment_by_instrument=source.size_increment_by_instrument,
    )
