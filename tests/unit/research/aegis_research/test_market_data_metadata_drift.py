"""Drift-detection tests for the market_data.v2 metadata model.

The typed model must reject unexpected fields at construction
(``extra="forbid"``) so that a new field added to the hand-written dict
but forgotten in the dataclass is caught immediately.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from research.aegis_research.market_data.contracts import MarketDataMetadataV2


def test_constructing_with_extra_field_is_rejected() -> None:
    """A drift-detection guard: unexpected keys fail at construction."""
    with pytest.raises(ValidationError):
        MarketDataMetadataV2(
            schema_version="market_data.v2",
            source="synthetic",
            provider_class=None,
            native_class=None,
            requested_symbols=["SYN"],
            symbols=[],
            features=[],
            canonical_features=[],
            authored_arrays=["Close"],
            effective_arrays=["Close"],
            required_arrays=["Close"],
            loaded_arrays=[],
            unavailable_arrays=["Close"],
            timeframe="1D",
            shape={"rows": 0, "symbols": 0, "features": 0, "columns": 0},
            ohlc_available={"Open": False, "High": False, "Low": False, "Close": False, "Volume": False},
            index_start=None,
            index_end=None,
            missing_index="raise",
            missing_columns="raise",
            tz_localize=None,
            tz_convert=None,
            skip_on_error=False,
            silence_warnings=False,
            quality={"state": "provider_failed", "reasons": [], "warnings": [], "allowed_degradations": []},
            diagnostics=[],
            source_metadata={},
            index_evidence={"source": "provider_failed"},
            provider_metadata={},
            omitted_metadata_fields=[],
            update_supported=False,
            cache_policy="disabled_in_schema_v2",
            # This field does not exist on the model:
            unexpected_field="should be rejected",  # type: ignore[call-arg]
        )
