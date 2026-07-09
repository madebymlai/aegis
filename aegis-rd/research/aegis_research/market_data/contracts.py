from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from aegis_data.distributions import Distribution
from aegis_runtime.currency import CurrencyConversion
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data.native_metadata import supports_update

LOGICAL_ARRAYS = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}
# The one source-metadata key naming the materialised synthetic continuous roots;
# written by the catalog adapter, read by the MarketDataResult mode invariant.
CONTINUOUS_ROOT_IDS_KEY = "continuous_root_ids"
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


class AdjustmentModeEvidenceError(ValueError):
    """A market-data result pairs futures evidence and adjustment mode incoherently."""


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
    # Non-base → base FX conversion derived from the catalog's resolved instruments and
    # ``exchange:`` FX series; ``None`` for a single-currency book (no ``exchange:``).
    currency_conversion: CurrencyConversion | None = None
    # The continuous-futures re-basing mode this pull materialised its synthetic
    # roots under — the exact enum supplied to materialisation, recorded as a Run
    # fact. ``None`` when no futures were materialised.
    adjustment_mode: ContinuousFutureAdjustmentType | None = None
    # Listed-ETF cash events read from the same Nautilus catalog as bars.
    distributions: tuple[Distribution, ...] = ()
    # Set only by ``provider_failed_adapter_result``: adapters raise
    # ``RemoteDataPullError``, they never return a failed result. Carrying the
    # failure as data lets the one observe → judge → describe sequence handle
    # both outcomes.
    failure: RemoteDataPullError | None = None

    @property
    def provider_class(self) -> str | None:
        return None if self.native_data is None else type(self.native_data).__name__

    @property
    def update_supported(self) -> bool:
        if self.native_data is None:
            return False
        return supports_update(self.native_data)


def provider_failed_adapter_result(error: RemoteDataPullError) -> MarketDataAdapterResult:
    """The degenerate result a failed pull collapses to: no native data,
    provider-failed index evidence, the error carried as data."""
    return MarketDataAdapterResult(
        native_data=None,
        evidence={"source": "provider_failed"},
        failure=error,
    )


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
    currency_conversion: CurrencyConversion | None = None
    adjustment_mode: ContinuousFutureAdjustmentType | None = None
    distributions: tuple[Distribution, ...] = ()

    def __post_init__(self) -> None:
        # Adjustment mode is a materialisation fact: it exists iff continuous
        # roots were materialised. A drifted pairing can only mean a wiring bug
        # upstream, so it fails here rather than becoming false Run evidence.
        roots = self.metadata.provenance.source_metadata.get(CONTINUOUS_ROOT_IDS_KEY) or ()
        if roots and self.adjustment_mode is None:
            raise AdjustmentModeEvidenceError(
                f"market data materialised continuous roots {list(roots)} but "
                "carries no adjustment_mode fact"
            )
        if self.adjustment_mode is not None and not roots:
            raise AdjustmentModeEvidenceError(
                "market data carries an adjustment_mode fact but materialised "
                "no continuous roots"
            )

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)
