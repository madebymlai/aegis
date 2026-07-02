from __future__ import annotations

import pandas as pd
from aegis_runtime import MarketDataBundle
from vectorbtpro import vbt

from research.aegis_research.configuration import OHLCV_ARRAYS
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import (
    LOGICAL_ARRAYS,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_PROVIDER_FAILED,
    QUALITY_REJECTED,
    DataArrayDiagnostics,
    DataDiagnostics,
    MarketDataAdapter,
    MarketDataAdapterResult,
    MarketDataQuality,
    MarketDataQualityError,
    MarketDataResult,
    RemoteDataPullError,
)
from research.aegis_research.market_data.features import (
    array_from_ohlcv,
    close_from_ohlcv,
    high_from_ohlcv,
    low_from_ohlcv,
    required_experiment_ohlcv_arrays,
    required_ohlcv_arrays,
)
from research.aegis_research.market_data.loading import (
    load_market_data,
    load_market_data_result,
)
from research.aegis_research.market_data.panels import market_data_bundle

__all__ = [
    "LOGICAL_ARRAYS",
    "OHLCV_ARRAYS",
    "QUALITY_DEGRADED_ALLOWED",
    "QUALITY_HEALTHY",
    "QUALITY_PROVIDER_FAILED",
    "QUALITY_REJECTED",
    "DataArrayDiagnostics",
    "DataDiagnostics",
    "MarketDataAdapter",
    "MarketDataAdapterResult",
    "MarketDataBundle",
    "MarketDataQuality",
    "MarketDataQualityError",
    "MarketDataResult",
    "RemoteDataPullError",
    "array_from_ohlcv",
    "close_from_ohlcv",
    "high_from_ohlcv",
    "load_catalog_source",
    "load_market_data",
    "load_market_data_result",
    "low_from_ohlcv",
    "market_data_bundle",
    "pd",
    "required_experiment_ohlcv_arrays",
    "required_ohlcv_arrays",
    "vbt",
]
