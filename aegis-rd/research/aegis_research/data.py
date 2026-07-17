from __future__ import annotations

import pandas as pd
from aegis_runtime import MarketDataBundle
from vectorbtpro import vbt

from research.aegis_research.configuration import OHLCV_ARRAYS
from research.aegis_research.market_data.contracts import (
    LOGICAL_ARRAYS,
    QUALITY_DATA_UNAVAILABLE,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_REJECTED,
    DataArrayDiagnostics,
    DataDiagnostics,
    MarketDataQuality,
    MarketDataQualityError,
    MarketDataResult,
    MarketDataUnavailableError,
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
from research.aegis_research.market_data.run_arrays import (
    RunArrayAlignmentError,
    RunArrays,
    prepare_run_arrays,
)

__all__ = [
    "LOGICAL_ARRAYS",
    "OHLCV_ARRAYS",
    "QUALITY_DATA_UNAVAILABLE",
    "QUALITY_DEGRADED_ALLOWED",
    "QUALITY_HEALTHY",
    "QUALITY_REJECTED",
    "DataArrayDiagnostics",
    "DataDiagnostics",
    "MarketDataBundle",
    "MarketDataQuality",
    "MarketDataQualityError",
    "MarketDataResult",
    "MarketDataUnavailableError",
    "RunArrayAlignmentError",
    "RunArrays",
    "array_from_ohlcv",
    "close_from_ohlcv",
    "high_from_ohlcv",
    "load_market_data",
    "load_market_data_result",
    "low_from_ohlcv",
    "market_data_bundle",
    "pd",
    "prepare_run_arrays",
    "required_experiment_ohlcv_arrays",
    "required_ohlcv_arrays",
    "vbt",
]
