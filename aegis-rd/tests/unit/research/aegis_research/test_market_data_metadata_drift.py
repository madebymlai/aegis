"""Drift-detection tests for the market_data.v4 metadata model.

The typed model must reject unexpected fields at construction
(``extra="forbid"``) so that a new field added but forgotten in the
dataclass is caught immediately.
"""

from __future__ import annotations

import pytest
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import ValidationError

from research.aegis_research.market_data.contracts import (
    ArrayDescriptor,
    CoverageFacet,
    DataDiagnostics,
    MarketDataMetadataV4,
    MarketDataQuality,
    ProvenanceFacet,
    RequestFacet,
)


def test_constructing_with_extra_field_is_rejected() -> None:
    """A drift-detection guard: unexpected keys fail at construction."""
    with pytest.raises(ValidationError):
        MarketDataMetadataV4(
            schema_version="market_data.v4",
            request=RequestFacet(
                requested_instrument_ids=[_id("SYN.XNAS")],
                timeframe="1D",
                authored_arrays=["Close"],
                effective_arrays=["Close"],
            ),
            arrays=[
                ArrayDescriptor(
                    name="Close", required=True, loaded=False, observed=False, ohlc=True
                )
            ],
            coverage=CoverageFacet(instrument_ids=[], rows=0, start=None, end=None),
            quality=MarketDataQuality(state="data_unavailable"),
            diagnostics=[],
            provenance=ProvenanceFacet(
                source_class=None,
                source_metadata={},
                index_evidence={"source": "data_unavailable"},
                port_metadata={},
                update_supported=False,
                missing_index="raise",
            ),
            # This field does not exist on the model:
            unexpected_field="should be rejected",  # type: ignore[call-arg]
        )


def test_diagnostics_rejects_primitive_instrument_id() -> None:
    with pytest.raises(ValidationError):
        DataDiagnostics(
            instrument_id="SYN.XNAS",  # type: ignore[arg-type]
            configured=True,
        )


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)
