from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.configuration import OHLCV_ARRAYS, DataConfig
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    local_provider_metadata,
    native_from_array_dict,
)
from research.aegis_research.market_data.contracts import (
    MarketDataAdapterResult,
)


def load_synthetic_source(config: DataConfig) -> MarketDataAdapterResult:
    native_data = _synthetic_data(config)
    projected = local_provider_metadata(native_data, source=config.source)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"generated": True, "seed": config.seed, "rows": config.rows},
        evidence=index_evidence(native_data.index, source="generated"),
        provider_metadata=projected["metadata"],
        omitted_metadata_fields=projected["omitted"],
    )


def _synthetic_data(config: DataConfig) -> Any:
    rng = np.random.default_rng(config.seed)
    index = pd.date_range(
        config.start or "2020-01-01",
        periods=config.rows,
        freq=config.timeframe,
        tz="UTC",
        name="Open time",
    )
    array_values: dict[str, dict[str, np.ndarray]] = {name: {} for name in OHLCV_ARRAYS}
    for symbol_idx, symbol in enumerate(config.symbols):
        drift = 0.00015 + symbol_idx * 0.00003
        volatility = 0.015 + symbol_idx * 0.002
        returns = rng.normal(drift, volatility, size=config.rows)
        close = 100 * np.cumprod(1 + returns)
        spread = np.abs(rng.normal(0.002, 0.001, size=config.rows))
        open_ = close * (1 + rng.normal(0, 0.001, size=config.rows))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.lognormal(mean=12, sigma=0.25, size=config.rows)
        array_values["Open"][symbol] = open_
        array_values["High"][symbol] = high
        array_values["Low"][symbol] = low
        array_values["Close"][symbol] = close
        array_values["Volume"][symbol] = volume
    return native_from_array_dict(
        {
            name: pd.DataFrame(values, index=index, columns=pd.Index(config.symbols))
            for name, values in array_values.items()
        },
        config,
    )
