from __future__ import annotations

import pandas as pd

from research.aegis_research.config import DataConfig
from research.aegis_research.data import (
    DataDiagnostics,
    DataFeatureDiagnostics,
    MarketDataAdapterResult,
    MarketDataQuality,
    RemoteDataPullError,
    load_market_data_result,
)
from research.aegis_research.market_data import loading as data_loading
from research.aegis_research.market_data import metadata as data_metadata
from tests.support.research.aegis_research.factories import make_data_config


def _frozen_observation() -> data_loading.MarketDataObservation:
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0]}, index=index)
    return data_loading.MarketDataObservation(
        index=index,
        features=("Close",),
        symbols=("SYN",),
        panels={"Close": close},
    )


class _FrozenData:
    feature_oriented = True

    def __init__(self) -> None:
        self.symbols = ["SYN"]
        self.index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
        self.features = ["Close"]

    def get(self, feature: str | None = None, **_kwargs) -> pd.DataFrame:
        frame = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=self.index)
        frame.columns = pd.MultiIndex.from_product(
            [self.symbols, frame.columns], names=["symbol", "feature"]
        )
        if feature is None:
            return frame
        return frame.xs(feature, axis=1, level="feature")


def test_describe_builds_the_schema_v2_metadata_dict_byte_identically() -> None:
    config = make_data_config(source="frozen", symbols=["SYN"], arrays=["Close"])
    observation = _frozen_observation()
    diagnostics = (
        DataDiagnostics(
            symbol="SYN",
            configured=True,
            features={
                "Close": DataFeatureDiagnostics(
                    available=True,
                    rows=3,
                    missing=0,
                    coverage=1.0,
                    numeric=True,
                    first_timestamp="2020-01-01 00:00:00+00:00",
                    last_timestamp="2020-01-03 00:00:00+00:00",
                )
            },
            index_evidence={"source": "test_evidence", "raw_rows": 3},
            provider_status="loaded",
        ),
    )
    quality = MarketDataQuality(state="healthy")

    metadata = data_metadata.describe(
        config,
        native_class="_FrozenData",
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        source_metadata={"frozen": True},
        evidence={"source": "test_evidence", "raw_rows": 3},
        provider_metadata={"source": "frozen", "class": f"{__name__}._FrozenData"},
        omitted_metadata_fields=[],
        update_supported=False,
        required_features=("Close",),
    )

    assert metadata == {
        "schema_version": "market_data.v2",
        "source": "frozen",
        "provider_class": "_FrozenData",
        "native_class": "_FrozenData",
        "requested_symbols": ["SYN"],
        "symbols": ["SYN"],
        "features": ["Close"],
        "canonical_features": ["Close"],
        "authored_arrays": ["Close"],
        "effective_arrays": ["Close"],
        "required_arrays": ["Close"],
        "loaded_arrays": ["Close"],
        "unavailable_arrays": [],
        "timeframe": "1D",
        "shape": {"rows": 3, "symbols": 1, "features": 1, "columns": 1},
        "ohlc_available": {
            "Open": False,
            "High": False,
            "Low": False,
            "Close": True,
            "Volume": False,
        },
        "index_start": "2020-01-01 00:00:00+00:00",
        "index_end": "2020-01-03 00:00:00+00:00",
        "missing_index": "raise",
        "missing_columns": "raise",
        "tz_localize": None,
        "tz_convert": None,
        "skip_on_error": False,
        "silence_warnings": False,
        "quality": {
            "state": "healthy",
            "reasons": [],
            "warnings": [],
            "allowed_degradations": [],
        },
        "diagnostics": [
            {
                "symbol": "SYN",
                "configured": True,
                "features": {
                    "Close": {
                        "available": True,
                        "rows": 3,
                        "missing": 0,
                        "coverage": 1.0,
                        "numeric": True,
                        "first_timestamp": "2020-01-01 00:00:00+00:00",
                        "last_timestamp": "2020-01-03 00:00:00+00:00",
                    }
                },
                "index_evidence": {"source": "test_evidence", "raw_rows": 3},
                "provider_status": "loaded",
            }
        ],
        "source_metadata": {"frozen": True},
        "index_evidence": {"source": "test_evidence", "raw_rows": 3},
        "provider_metadata": {
            "source": "frozen",
            "class": f"{__name__}._FrozenData",
        },
        "omitted_metadata_fields": [],
        "update_supported": False,
        "cache_policy": "disabled_in_schema_v2",
    }


def test_provider_failure_routes_through_the_same_describe_builder() -> None:
    config = make_data_config(source="future", symbols=["SYN"], arrays=["Close"])
    quality = MarketDataQuality(
        state="provider_failed",
        reasons=("future provider failed before usable native data was available",),
    )
    diagnostics = (
        DataDiagnostics(
            symbol="SYN",
            configured=True,
            index_evidence={"source": "provider_failed"},
            provider_status="provider_failed",
        ),
    )

    expected = data_metadata.describe(
        config,
        native_class=None,
        observation=MarketDataObservation_empty(),
        diagnostics=diagnostics,
        quality=quality,
        source_metadata={
            "provider_error_type": "RemoteDataPullError",
            "provider_error_summary": (
                "future provider failed before usable native data was available"
            ),
        },
        evidence={"source": "provider_failed"},
        provider_metadata={},
        omitted_metadata_fields=[],
        update_supported=False,
        required_features=("Close", "OpenInterest"),
    )

    def fail(_config: DataConfig) -> MarketDataAdapterResult:
        raise RemoteDataPullError("future", "network unavailable")

    result = load_market_data_result(
        config,
        required_features=("OpenInterest",),
        adapters={"future": fail},
    )

    assert result.metadata == expected


def test_failed_shape_equals_success_shape_minus_data() -> None:
    success = load_market_data_result(
        make_data_config(source="frozen", symbols=["SYN"], arrays=["Close"]),
        adapters={
            "frozen": lambda _config: MarketDataAdapterResult(
                native_data=_FrozenData(),
                source_metadata={"frozen": True},
                evidence={"source": "test_evidence", "raw_rows": 3},
            )
        },
    )

    def fail(_config: DataConfig) -> MarketDataAdapterResult:
        raise RemoteDataPullError("frozen", "network unavailable")

    failure = load_market_data_result(
        make_data_config(source="frozen", symbols=["SYN"], arrays=["Close"]),
        adapters={"frozen": fail},
    )

    assert list(failure.metadata.keys()) == list(success.metadata.keys())
    assert failure.metadata["symbols"] == []
    assert failure.metadata["loaded_arrays"] == []
    assert failure.metadata["shape"] == {
        "rows": 0,
        "symbols": 0,
        "features": 0,
        "columns": 0,
    }
    assert failure.metadata["provider_class"] is None
    assert failure.metadata["native_class"] is None
    assert failure.metadata["quality"]["state"] == "provider_failed"
    assert failure.native_data is None


def test_describe_tolerates_empty_provider_internals() -> None:
    config = make_data_config(source="future", symbols=["SYN"], arrays=["Close"])

    metadata = data_metadata.describe(
        config,
        native_class=None,
        observation=MarketDataObservation_empty(),
        diagnostics=(),
        quality=MarketDataQuality(state="provider_failed"),
        source_metadata={},
        evidence={"source": "provider_failed"},
        provider_metadata={},
        omitted_metadata_fields=[],
        update_supported=False,
        required_features=("Close",),
    )

    assert metadata["provider_class"] is None
    assert metadata["native_class"] is None
    assert metadata["provider_metadata"] == {}
    assert metadata["omitted_metadata_fields"] == []
    assert metadata["update_supported"] is False
    assert metadata["shape"] == {"rows": 0, "symbols": 0, "features": 0, "columns": 0}


def MarketDataObservation_empty() -> data_metadata.MarketDataObservation:
    return data_metadata.MarketDataObservation(
        index=pd.Index([]),
        features=(),
        symbols=(),
        panels={},
    )


def test_loaded_metadata_round_trips_through_the_public_loader() -> None:
    native_data = _FrozenData()

    result = load_market_data_result(
        make_data_config(source="frozen", symbols=["SYN"], arrays=["Close"]),
        adapters={
            "frozen": lambda _config: MarketDataAdapterResult(
                native_data=native_data,
                source_metadata={"frozen": True},
                evidence={"source": "test_evidence", "raw_rows": 3},
                provider_metadata={"source": "frozen", "class": f"{__name__}._FrozenData"},
            )
        },
    )

    assert result.metadata["loaded_arrays"] == ["Close"]
    assert result.metadata["source_metadata"] == {"frozen": True}
    assert result.metadata["provider_metadata"]["class"] == f"{__name__}._FrozenData"
