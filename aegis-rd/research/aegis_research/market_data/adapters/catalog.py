"""Nautilus catalog-backed RD market-data adapter."""

from __future__ import annotations

import pandas as pd
from aegis_data.catalog import (
    CatalogBackedDataPort,
    RawBarRequest,
    catalog_data_port,
)
from aegis_data.continuous_catalog import continuous_ohlcv_frames
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
    # ADR-0006: research fills like live — a catalog miss backfills through the
    # port (unconditional, ungated); a warm read never connects. The concrete
    # provider is wired inside aegis-data's factory, so this module depends only on
    # the CatalogBackedDataPort abstraction (DIP).
    data_port = port if port is not None else catalog_data_port(config.path)
    start = _required_window_edge(config.start, "start")
    end = _required_window_edge(config.end, "end")
    raw_frames = data_port.load_raw_bars(
        RawBarRequest(
            instrument_ids=instrument_ids(config.native_instrument_ids),
            start=start,
            end=end,
            timeframe=config.timeframe,
        )
    )
    # Continuous-future roots are synthetic: aegis-data materialises each as an adjusted
    # series on demand (Path A) and hands it back as an OHLCV frame keyed by its root id,
    # so it merges into native_data exactly like a raw leg — first-class through the same
    # diagnostics/quality/bundle path, never persisted.
    continuous_frames = continuous_ohlcv_frames(
        data_port, config.futures, start=start, end=end, timeframe=config.timeframe
    )
    collisions = set(raw_frames) & set(continuous_frames)
    if collisions:
        raise ValueError(
            "continuous-future root ids collide with raw instrument ids: "
            f"{sorted(instrument_id.value for instrument_id in collisions)}"
        )
    frames = {**raw_frames, **continuous_frames}
    tradeable_instrument_ids = (*instrument_ids(config.instruments), *continuous_frames)
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
            "continuous_root_ids": [root_id.value for root_id in continuous_frames],
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
