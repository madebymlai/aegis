from __future__ import annotations

import importlib

from research.aegis_research import data as facade

# The frozen public surface of research.aegis_research.data — the deep
# interface after the adapter-seam retirement (aegis-rd-1gef.5): the load
# entry points, the result and its typed parts, the quality-state vocabulary,
# and the one environmental error. The catalog loader and the internal load
# handoff are implementation, not interface.
EXPECTED_PUBLIC_NAMES = (
    "LOGICAL_ARRAYS",
    "OHLCV_ARRAYS",
    "QUALITY_DATA_UNAVAILABLE",
    "QUALITY_DEGRADED_ALLOWED",
    "QUALITY_HEALTHY",
    "QUALITY_REJECTED",
    "DataDiagnostics",
    "DataArrayDiagnostics",
    "MarketDataBundle",
    "MarketDataQuality",
    "MarketDataQualityError",
    "MarketDataResult",
    "MarketDataUnavailableError",
    "RunArrayAlignmentError",
    "RunArrays",
    "close_from_ohlcv",
    "array_from_ohlcv",
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
)


def test_facade_all_surface_is_unchanged() -> None:
    assert sorted(facade.__all__) == sorted(EXPECTED_PUBLIC_NAMES)


def test_every_public_name_imports_from_the_facade() -> None:
    fresh = importlib.import_module("research.aegis_research.data")
    for name in EXPECTED_PUBLIC_NAMES:
        assert hasattr(fresh, name), f"facade no longer exposes {name!r}"
        assert getattr(fresh, name) is not None
