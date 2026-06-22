"""Nautilus catalog-backed RD market-data adapter."""

from __future__ import annotations

import pandas as pd
from aegis_data.catalog import (
    CatalogBackedDataPort,
    RawBarRequest,
    parquet_data_catalog,
)
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
    native_index,
)
from research.aegis_research.market_data.contracts import MarketDataAdapterResult
from research.aegis_research.market_data.identity import instrument_ids


def load_catalog_source(
    config: DataConfig,
    *,
    port: CatalogBackedDataPort | None = None,
) -> MarketDataAdapterResult:
    data_port = port if port is not None else CatalogBackedDataPort(parquet_data_catalog(config.path))
    requested_instrument_ids = instrument_ids(config.native_instrument_ids)
    frames = data_port.load_raw_bars(
        RawBarRequest(
            instrument_ids=requested_instrument_ids,
            start=_required_window_edge(config.start, "start"),
            end=_required_window_edge(config.end, "end"),
            timeframe=config.timeframe,
        )
    )
    tradeable_instrument_ids = instrument_ids(config.instruments)
    native_data = native_from_array_dict(
        _array_panels(config, frames, tradeable_instrument_ids), config
    )
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={
            "catalog_path": config.path,
            "requested_instrument_ids": list(config.native_instrument_ids),
            "tradeable_instrument_ids": list(config.instruments),
            "exchange_instrument_ids": list(config.exchange),
        },
        evidence=index_evidence(native_index(native_data), source="nautilus_catalog"),
        provider_metadata={"source": "nautilus_data_provider_port"},
    )


def _array_panels(
    config: DataConfig,
    frames: dict[InstrumentId, pd.DataFrame],
    instrument_ids: tuple[InstrumentId, ...],
) -> dict[str, pd.DataFrame]:
    return {
        array: pd.DataFrame(
            {
                instrument_id: frames[instrument_id][array]
                for instrument_id in instrument_ids
            }
        )
        for array in config.effective_arrays
    }


def _required_window_edge(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required for catalog source")
    return value


__all__ = ["load_catalog_source"]
