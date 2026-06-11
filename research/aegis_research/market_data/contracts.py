from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration import OHLCV_ARRAYS, DataConfig

OHLCV_FEATURES = OHLCV_ARRAYS
LOGICAL_FEATURES = {
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


@dataclass(frozen=True)
class MarketDataQuality:
    state: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    allowed_degradations: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state in {QUALITY_HEALTHY, QUALITY_DEGRADED_ALLOWED}

    def to_metadata(self) -> dict[str, Any]:
        return to_builtin(self)


@dataclass(frozen=True)
class MarketDataAdapterResult:
    native_data: Any
    source_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    omitted_metadata_fields: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class DataFeatureDiagnostics:
    available: bool
    rows: int = 0
    missing: int = 0
    coverage: float = 0.0
    numeric: bool | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False}
        return to_builtin(
            {
                "available": True,
                "rows": self.rows,
                "missing": self.missing,
                "coverage": self.coverage,
                "numeric": self.numeric,
                "first_timestamp": self.first_timestamp,
                "last_timestamp": self.last_timestamp,
            }
        )


@dataclass(frozen=True)
class DataDiagnostics:
    symbol: str
    configured: bool
    features: dict[str, DataFeatureDiagnostics] = field(default_factory=dict)
    index_evidence: dict[str, Any] = field(default_factory=dict)
    provider_status: str = "loaded"

    def to_metadata(self) -> dict[str, Any]:
        return to_builtin(
            {
                "symbol": self.symbol,
                "configured": self.configured,
                "features": {
                    feature: diagnostics.to_metadata()
                    for feature, diagnostics in self.features.items()
                },
                "index_evidence": self.index_evidence,
                "provider_status": self.provider_status,
            }
        )


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class MarketDataMetadataV2:
    """Typed ``market_data.v2`` metadata Evidence artifact.

    Frozen pydantic dataclass with ``extra="forbid"`` — the same idiom as the
    config schema (ADR-0012).  Every field the hand-built dict has carried.
    Serialization routes through ``to_builtin``; the keys and values are
    byte-identical to the pre-typed hand-built dict.
    """

    schema_version: str
    source: str
    provider_class: str | None
    native_class: str | None
    requested_symbols: list[str]
    symbols: list[str]
    features: list[str]
    canonical_features: list[str]
    authored_arrays: list[str]
    effective_arrays: list[str]
    required_arrays: list[str]
    loaded_arrays: list[str]
    unavailable_arrays: list[str]
    timeframe: str
    shape: dict[str, int]
    ohlc_available: dict[str, bool]
    index_start: str | None
    index_end: str | None
    missing_index: str
    missing_columns: str
    tz_localize: str | bool | None
    tz_convert: str | bool | None
    skip_on_error: bool
    silence_warnings: bool
    quality: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    source_metadata: dict[str, Any]
    index_evidence: dict[str, Any]
    provider_metadata: dict[str, Any]
    omitted_metadata_fields: list[dict[str, str]]
    update_supported: bool
    cache_policy: str


@dataclass(frozen=True)
class MarketDataResult:
    native_data: Any
    metadata: dict[str, Any]
    diagnostics: tuple[DataDiagnostics, ...]
    quality: MarketDataQuality

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)


@dataclass(frozen=True)
class MarketDataBundle:
    """Eager value object of materialised Array panels.

    Dict membership is the sole guard — a feature is loaded iff it is a key.
    """

    features: dict[str, pd.DataFrame]

    def feature(self, feature: str) -> pd.DataFrame:
        try:
            return self.features[feature]
        except KeyError:
            raise ValueError(
                f"market data feature {feature!r} was not loaded for this run"
            ) from None
