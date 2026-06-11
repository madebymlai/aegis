from __future__ import annotations

import pandas as pd

from research.aegis_research.configuration import DataConfig
from research.aegis_research.data import (
    DataDiagnostics,
    DataArrayDiagnostics,
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
        arrays=("Close",),
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
            arrays={
                "Close": DataArrayDiagnostics(
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
        required_arrays=("Close",),
    )

    # v3 facet-shaped model (ADR-0020): assert facets, not a flat dict
    assert metadata.schema_version == "market_data.v3"
    assert metadata.request.source == "frozen"
    assert metadata.request.requested_symbols == ["SYN"]
    assert metadata.request.timeframe == "1D"
    assert metadata.request.authored_arrays == ["Close"]
    assert metadata.request.effective_arrays == ["Close"]
    # One arrays descriptor list replaces eight parallel lists
    close_desc = next(d for d in metadata.arrays if d.name == "Close")
    assert close_desc.required is True
    assert close_desc.loaded is True
    assert close_desc.observed is True
    assert close_desc.ohlc is True
    # coverage facet
    assert metadata.coverage.symbols == ["SYN"]
    assert metadata.coverage.rows == 3
    assert metadata.coverage.start == "2020-01-01 00:00:00+00:00"
    assert metadata.coverage.end == "2020-01-03 00:00:00+00:00"
    # quality and diagnostics unchanged
    assert metadata.quality == {
        "state": "healthy",
        "reasons": [],
        "warnings": [],
        "allowed_degradations": [],
    }
    assert metadata.diagnostics == [
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
    ]
    # provenance facet: deduplicated provider/source blobs
    assert metadata.provenance.provider_class == "_FrozenData"
    assert metadata.provenance.source_metadata == {"frozen": True}
    assert metadata.provenance.index_evidence == {"source": "test_evidence", "raw_rows": 3}
    assert metadata.provenance.provider_metadata == {
        "source": "frozen",
        "class": f"{__name__}._FrozenData",
    }
    assert metadata.provenance.omitted_metadata_fields == []
    assert metadata.provenance.update_supported is False
    assert metadata.provenance.missing_index == "raise"
    assert metadata.provenance.missing_columns == "raise"
    assert metadata.provenance.tz_localize is None
    assert metadata.provenance.tz_convert is None
    assert metadata.provenance.skip_on_error is False
    assert metadata.provenance.silence_warnings is False


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
        required_arrays=("Close", "OpenInterest"),
    )

    def fail(_config: DataConfig) -> MarketDataAdapterResult:
        raise RemoteDataPullError("future", "network unavailable")

    result = load_market_data_result(
        config,
        required_arrays=("OpenInterest",),
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

    assert failure.metadata.schema_version == success.metadata.schema_version
    assert failure.metadata.coverage.symbols == []
    loaded = [d.name for d in failure.metadata.arrays if d.loaded]
    assert loaded == []
    assert failure.metadata.coverage.rows == 0
    assert failure.metadata.coverage.start is None
    assert failure.metadata.coverage.end is None
    assert failure.metadata.provenance.provider_class is None
    assert failure.metadata.quality["state"] == "provider_failed"
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
        required_arrays=("Close",),
    )

    assert metadata.provenance.provider_class is None
    assert metadata.provenance.provider_metadata == {}
    assert metadata.provenance.omitted_metadata_fields == []
    assert metadata.provenance.update_supported is False
    assert metadata.coverage.rows == 0
    assert metadata.coverage.symbols == []
    assert metadata.coverage.start is None
    assert metadata.coverage.end is None


def MarketDataObservation_empty() -> data_metadata.MarketDataObservation:
    return data_metadata.MarketDataObservation(
        index=pd.Index([]),
        arrays=(),
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

    loaded = [d.name for d in result.metadata.arrays if d.loaded]
    assert loaded == ["Close"]
    assert result.metadata.provenance.source_metadata == {"frozen": True}
    assert result.metadata.provenance.provider_metadata["class"] == f"{__name__}._FrozenData"
