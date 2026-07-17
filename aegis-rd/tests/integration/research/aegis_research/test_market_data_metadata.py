from __future__ import annotations

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.data import (
    DataArrayDiagnostics,
    DataDiagnostics,
    MarketDataQuality,
    load_market_data_result,
)
from research.aegis_research.market_data import loading as data_loading
from research.aegis_research.market_data import metadata as data_metadata
from research.aegis_research.market_data.contracts import (
    QUALITY_DATA_UNAVAILABLE,
    MarketDataLoad,
)
from tests.support.research.aegis_research.factories import make_data_config
from tests.support.research.aegis_research.market_data_fixtures import (
    result_from_load,
    unservable_port,
)


def _frozen_observation() -> data_loading.MarketDataObservation:
    index = pd.date_range("2020-01-01", periods=3, tz="UTC", name="Open time")
    close = pd.DataFrame({_id("SYN.XNAS"): [1.0, 2.0, 3.0]}, index=index)
    return data_loading.MarketDataObservation(
        index=index,
        arrays=("Close",),
        instrument_ids=(_id("SYN.XNAS"),),
        panels={"Close": close},
    )


class _FrozenData:
    feature_oriented = True

    def __init__(self) -> None:
        self.symbols = [_id("SYN.XNAS")]
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


def test_describe_builds_the_market_data_v4_facet_model() -> None:
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])
    observation = _frozen_observation()
    diagnostics = (
        DataDiagnostics(
            instrument_id=_id("SYN.XNAS"),
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
            load_status="loaded",
        ),
    )
    quality = MarketDataQuality(state="healthy")

    metadata = data_metadata.describe(
        config,
        source=MarketDataLoad(
            native_data=_FrozenData(),
            source_metadata={"frozen": True},
            evidence={"source": "test_evidence", "raw_rows": 3},
            port_metadata={"source": "frozen", "class": f"{__name__}._FrozenData"},
        ),
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        required_arrays=("Close",),
    )

    # v4 facet-shaped model (ADR-0020): assert facets, not a flat dict
    assert metadata.schema_version == "market_data.v4"
    assert metadata.request.requested_instrument_ids == [_id("SYN.XNAS")]
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
    assert metadata.coverage.instrument_ids == [_id("SYN.XNAS")]
    assert metadata.coverage.rows == 3
    assert metadata.coverage.start == "2020-01-01 00:00:00+00:00"
    assert metadata.coverage.end == "2020-01-03 00:00:00+00:00"
    # quality and diagnostics are the typed records themselves
    assert metadata.quality == quality
    assert metadata.diagnostics == list(diagnostics)
    # the serialized wire shape speaks Array, with one uniform per-Array shape
    wire = to_builtin(metadata)
    assert wire["quality"] == {
        "state": "healthy",
        "reasons": [],
        "warnings": [],
        "allowed_degradations": [],
    }
    assert wire["diagnostics"] == [
        {
            "instrument_id": "SYN.XNAS",
            "configured": True,
            "arrays": {
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
            "load_status": "loaded",
        }
    ]
    # provenance facet: deduplicated provider/source blobs
    assert metadata.provenance.source_class == "_FrozenData"
    assert metadata.provenance.source_metadata == {"frozen": True}
    assert metadata.provenance.index_evidence == {"source": "test_evidence", "raw_rows": 3}
    assert metadata.provenance.port_metadata == {
        "source": "frozen",
        "class": f"{__name__}._FrozenData",
    }
    assert metadata.provenance.update_supported is False
    assert metadata.provenance.missing_index == "raise"


def test_unavailable_failure_wire_shape_is_pinned() -> None:
    """The failure provenance a Run records when its window cannot be served:
    the error type and the gate's judgement in source metadata, the
    data-unavailable evidence marker, and provider internals collapsed to
    their empty values."""
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])

    result = load_market_data_result(config, port=unservable_port())

    assert result.metadata.provenance.source_metadata["error_type"] == (
        "MarketDataUnavailableError"
    )
    assert "missing=" in result.metadata.provenance.source_metadata[
        "error_summary"
    ]
    assert result.metadata.provenance.index_evidence["source"] == (
        QUALITY_DATA_UNAVAILABLE
    )
    assert result.metadata.provenance.port_metadata == {}
    assert result.metadata.provenance.update_supported is False
    assert result.metadata.provenance.source_class is None


def test_failed_shape_equals_success_shape_minus_data() -> None:
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])
    success = result_from_load(
        config,
        MarketDataLoad(
            native_data=_FrozenData(),
            source_metadata={"frozen": True},
            evidence={"source": "test_evidence", "raw_rows": 3},
        ),
    )

    failure = load_market_data_result(config, port=unservable_port())

    assert failure.metadata.schema_version == success.metadata.schema_version
    assert failure.metadata.coverage.instrument_ids == []
    loaded = [d.name for d in failure.metadata.arrays if d.loaded]
    assert loaded == []
    assert failure.metadata.coverage.rows == 0
    assert failure.metadata.coverage.start is None
    assert failure.metadata.coverage.end is None
    assert failure.metadata.provenance.source_class is None
    assert failure.metadata.quality.state == QUALITY_DATA_UNAVAILABLE
    assert failure.native_data is None


def test_describe_tolerates_empty_provider_internals() -> None:
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])

    metadata = data_metadata.describe(
        config,
        source=MarketDataLoad(
            native_data=None,
            evidence={"source": QUALITY_DATA_UNAVAILABLE},
        ),
        observation=MarketDataObservation_empty(),
        diagnostics=(),
        quality=MarketDataQuality(state=QUALITY_DATA_UNAVAILABLE),
        required_arrays=("Close",),
    )

    assert metadata.provenance.source_class is None
    assert metadata.provenance.port_metadata == {}
    assert metadata.provenance.update_supported is False
    assert metadata.coverage.rows == 0
    assert metadata.coverage.instrument_ids == []
    assert metadata.coverage.start is None
    assert metadata.coverage.end is None


def MarketDataObservation_empty() -> data_metadata.MarketDataObservation:
    return data_metadata.MarketDataObservation(
        index=pd.Index([]),
        arrays=(),
        instrument_ids=(),
        panels={},
    )


def test_loaded_metadata_round_trips_through_the_leaf_sequence() -> None:
    native_data = _FrozenData()

    result = result_from_load(
        make_data_config(instruments=["SYN.XNAS"], arrays=["Close"]),
        MarketDataLoad(
            native_data=native_data,
            source_metadata={"frozen": True},
            evidence={"source": "test_evidence", "raw_rows": 3},
            port_metadata={"source": "frozen", "class": f"{__name__}._FrozenData"},
        ),
    )

    loaded = [d.name for d in result.metadata.arrays if d.loaded]
    assert loaded == ["Close"]
    assert result.metadata.provenance.source_metadata == {"frozen": True}
    assert result.metadata.provenance.port_metadata["class"] == f"{__name__}._FrozenData"


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)
