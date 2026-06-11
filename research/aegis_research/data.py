from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.market_data.adapters.remote import (
    SAFE_FETCH_KWARG_KEYS,
    SAFE_RETURNED_KWARG_KEYS,
    _pull_remote,
)
from research.aegis_research.market_data.contracts import (
    LOGICAL_FEATURES,
    OHLCV_FEATURES,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_PROVIDER_FAILED,
    QUALITY_REJECTED,
    DataDiagnostics,
    DataFeatureDiagnostics,
    MarketDataAdapter,
    MarketDataAdapterResult,
    MarketDataBundle,
    MarketDataQuality,
    MarketDataQualityError,
    MarketDataResult,
    RemoteDataPullError,
)
from research.aegis_research.market_data.panels import market_data_bundle
from research.aegis_research.market_data.features import (
    close_from_ohlcv,
    feature_from_ohlcv,
    high_from_ohlcv,
    low_from_ohlcv,
    required_experiment_ohlcv_features,
    required_ohlcv_features,
)
from research.aegis_research.market_data.loading import (
    load_market_data,
    load_market_data_result,
)
from research.aegis_research.market_data.sources import REMOTE_DATA_CLASSES

__all__ = [
    "LOGICAL_FEATURES",
    "OHLCV_FEATURES",
    "QUALITY_DEGRADED_ALLOWED",
    "QUALITY_HEALTHY",
    "QUALITY_PROVIDER_FAILED",
    "QUALITY_REJECTED",
    "REMOTE_DATA_CLASSES",
    "SAFE_FETCH_KWARG_KEYS",
    "SAFE_RETURNED_KWARG_KEYS",
    "DataDiagnostics",
    "DataFeatureDiagnostics",
    "MarketDataAdapter",
    "MarketDataAdapterResult",
    "MarketDataBundle",
    "MarketDataQuality",
    "MarketDataQualityError",
    "MarketDataResult",
    "RemoteDataPullError",
    "_pull_remote",
    "close_from_ohlcv",
    "feature_from_ohlcv",
    "high_from_ohlcv",
    "load_market_data",
    "load_market_data_result",
    "low_from_ohlcv",
    "market_data_bundle",
    "pd",
    "required_experiment_ohlcv_features",
    "required_ohlcv_features",
    "vbt",
]
