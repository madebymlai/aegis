from __future__ import annotations

import importlib

from research.aegis_research import data as facade

# The frozen public surface of research.aegis_research.data. The market-data
# decomposition moves concerns between leaf modules but must keep this facade
# byte-for-byte stable: every name below stays importable, with the same object,
# so nothing outside market_data/ has to change.
EXPECTED_PUBLIC_NAMES = (
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
    "assert_public_metadata_safe",
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
)


def test_facade_all_surface_is_unchanged() -> None:
    assert sorted(facade.__all__) == sorted(EXPECTED_PUBLIC_NAMES)


def test_every_public_name_imports_from_the_facade() -> None:
    fresh = importlib.import_module("research.aegis_research.data")
    for name in EXPECTED_PUBLIC_NAMES:
        assert hasattr(fresh, name), f"facade no longer exposes {name!r}"
        assert getattr(fresh, name) is not None
