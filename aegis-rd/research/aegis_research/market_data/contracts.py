from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from aegis_data.distributions import Distribution
from aegis_runtime.currency import CurrencyConversion
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

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
QUALITY_DATA_UNAVAILABLE = "data_unavailable"
# Carried in the failed load's index evidence so the judge — which reads only
# diagnostics and evidence, never the load itself — can put the gate's exact
# judgement (which intervals cannot be served) into the verdict's reasons.
UNAVAILABLE_REASON_KEY = "unavailable_reason"


class MarketDataUnavailableError(RuntimeError):
    """The Run's market data cannot be served for environmental reasons.

    Raised by the catalog loader when the port judges the requested window
    unservable (a coverage gap after backfill) or the gap fill itself faults
    (gateway drop, dead vendor call), with the port error chained as the cause.
    The loading orchestrator catches exactly this error and collapses it into
    failure Evidence — authoring errors are never wrapped and keep crashing.
    """


class MarketDataQualityError(ValueError):
    def __init__(self, quality: MarketDataQuality) -> None:
        self.quality = quality
        details = "; ".join(quality.reasons) or quality.state
        super().__init__(f"Market data quality check failed: {details}")


class AdjustmentModeEvidenceError(ValueError):
    """A market-data result pairs futures evidence and adjustment mode incoherently."""


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
class MarketDataLoad:
    """One load outcome — the internal handoff observe → judge → describe read."""

    native_data: Any
    source_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    port_metadata: dict[str, Any] = field(default_factory=dict)
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
    # Set only by ``failed_market_data_load``: the loader raises, it never
    # returns a failed load. Carrying the failure as data lets the one
    # observe → judge → describe sequence handle both outcomes.
    failure: MarketDataUnavailableError | None = None

    @property
    def source_class(self) -> str | None:
        return None if self.native_data is None else type(self.native_data).__name__

    @property
    def update_supported(self) -> bool:
        if self.native_data is None:
            return False
        return supports_update(self.native_data)


def failed_market_data_load(error: MarketDataUnavailableError) -> MarketDataLoad:
    """The degenerate load an unavailable window collapses to: no native data,
    data-unavailable index evidence carrying the gate's judgement, the error as
    data."""
    return MarketDataLoad(
        native_data=None,
        evidence={
            "source": QUALITY_DATA_UNAVAILABLE,
            UNAVAILABLE_REASON_KEY: str(error),
        },
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
    load_status: str = "loaded"


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
    """Source/port blobs and the one loader policy carried forward.

    Reshaped for ``market_data.v4``: catalog-era vocabulary only — the retired
    remote/VBT-loader knobs are gone and the ``provider_*`` names became
    ``source_class`` / ``port_metadata``.
    """

    source_class: str | None
    source_metadata: dict[str, Any]
    index_evidence: dict[str, Any]
    port_metadata: dict[str, Any]
    update_supported: bool
    missing_index: str


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class MarketDataMetadataV4:
    """Typed ``market_data.v4`` metadata Evidence artifact.

    Facet-shaped model (ADR-0020); the v4 reshape retires the remote/VBT-era
    vocabulary alongside the adapter seam: provenance speaks catalog
    (``source_class`` / ``port_metadata``), per-instrument records carry a
    ``load_status``, and failure values say ``data_unavailable``.
    """

    schema_version: Literal["market_data.v4"]
    request: RequestFacet
    arrays: list[ArrayDescriptor]
    coverage: CoverageFacet
    quality: MarketDataQuality
    diagnostics: list[DataDiagnostics]
    provenance: ProvenanceFacet


@dataclass(frozen=True)
class MarketDataResult:
    native_data: Any
    metadata: MarketDataMetadataV4
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
