from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from nautilus_trader.model.identifiers import InstrumentId
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.configuration import DataConfig

LOGICAL_ARRAYS = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}
QUALITY_HEALTHY = "healthy"
QUALITY_DEGRADED_ALLOWED = "degraded_allowed"
QUALITY_REJECTED = "rejected"
QUALITY_PROVIDER_FAILED = "provider_failed"


class RemoteDataPullError(ValueError):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"Failed to pull {source} data: {message}")


class MarketDataQualityError(ValueError):
    def __init__(self, quality: MarketDataQuality) -> None:
        self.quality = quality
        details = "; ".join(quality.reasons) or quality.state
        super().__init__(f"Market data quality check failed: {details}")


class MarketDataAdapter(Protocol):
    def __call__(self, config: DataConfig) -> MarketDataAdapterResult: ...


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class MarketDataQuality:
    """The judge's verdict; serialises field-by-field as the ``quality`` facet."""

    state: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    allowed_degradations: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state in {QUALITY_HEALTHY, QUALITY_DEGRADED_ALLOWED}


@dataclass(frozen=True)
class MarketDataAdapterResult:
    native_data: Any
    source_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    omitted_metadata_fields: list[dict[str, str]] = field(default_factory=list)
    # Optional second continuous series (the ``pnl_adjustment`` mode) the portfolio
    # simulates P&L on; ``None`` when no instrument declares a P&L series.
    pnl_native_data: Any = None


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class DataArrayDiagnostics:
    """Per-Array column metrics; one uniform shape whether or not the Array
    was available (an unavailable Array keeps the empty-observation values)."""

    available: bool
    rows: int = 0
    missing: int = 0
    coverage: float = 0.0
    numeric: bool | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None


@pydantic_dataclass(
    frozen=True,
    config=ConfigDict(extra="forbid", arbitrary_types_allowed=True),
)
class DataDiagnostics:
    """Per-instrument observation record; serialises field-by-field as one entry
    of the ``diagnostics`` facet.

    Index evidence is observation-level, not per-instrument; it lives once, in
    the ``provenance`` facet.
    """

    instrument_id: InstrumentId
    configured: bool
    arrays: dict[str, DataArrayDiagnostics] = field(default_factory=dict)
    provider_status: str = "loaded"


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ArrayDescriptor:
    """One row in the ``arrays`` descriptor list."""

    name: str
    required: bool
    loaded: bool
    observed: bool
    ohlc: bool


@pydantic_dataclass(
    frozen=True,
    config=ConfigDict(extra="forbid", arbitrary_types_allowed=True),
)
class RequestFacet:
    """What was asked for: native InstrumentIds, timeframe, array declarations."""

    requested_instrument_ids: list[InstrumentId]
    timeframe: str
    authored_arrays: list[str]
    effective_arrays: list[str]


@pydantic_dataclass(
    frozen=True,
    config=ConfigDict(extra="forbid", arbitrary_types_allowed=True),
)
class CoverageFacet:
    """What was actually observed: instrument-id set, row count, index span."""

    instrument_ids: list[InstrumentId]
    rows: int
    start: str | None
    end: str | None


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ProvenanceFacet:
    """Provider/source blobs and loader configuration carried forward."""

    provider_class: str | None
    source_metadata: dict[str, Any]
    index_evidence: dict[str, Any]
    provider_metadata: dict[str, Any]
    omitted_metadata_fields: list[dict[str, str]]
    update_supported: bool
    missing_index: str
    missing_columns: str
    tz_localize: str | bool | None
    tz_convert: str | bool | None
    skip_on_error: bool
    silence_warnings: bool


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class MarketDataMetadataV3:
    """Typed ``market_data.v3`` metadata Evidence artifact.

    Facet-shaped model (ADR-0020) replacing the hand-built ``market_data.v2``
    dict.  One ``arrays`` descriptor list replaces eight parallel Array-name
    lists; duplicate, derivable, and vestigial keys are dropped.
    """

    schema_version: Literal["market_data.v3"]
    request: RequestFacet
    arrays: list[ArrayDescriptor]
    coverage: CoverageFacet
    quality: MarketDataQuality
    diagnostics: list[DataDiagnostics]
    provenance: ProvenanceFacet


@dataclass(frozen=True)
class MarketDataResult:
    native_data: Any
    metadata: MarketDataMetadataV3
    diagnostics: tuple[DataDiagnostics, ...]
    quality: MarketDataQuality
    pnl_native_data: Any = None

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)
