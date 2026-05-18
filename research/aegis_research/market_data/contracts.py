from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import pandas as pd

from research.aegis_research.configuration.schema import DataConfig
from research.aegis_research.configuration.secrets import to_builtin

OHLCV_FEATURES = ("Open", "High", "Low", "Close", "Volume")
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
SAFE_FETCH_KWARG_KEYS = {
    "delay",
    "end",
    "exchange",
    "find_earliest_date",
    "klines_type",
    "limit",
    "period",
    "retries",
    "start",
    "timeframe",
    "tz",
}
SAFE_RETURNED_KWARG_KEYS = {"freq", "tz", "tz_convert", "tz_localize"}


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
        return to_builtin(asdict(self))


@dataclass(frozen=True)
class MarketDataAdapterResult:
    native_data: Any
    known_secrets: tuple[str, ...] = ()
    source_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataResult:
    native_data: Any
    metadata: dict[str, Any]
    diagnostics: tuple[dict[str, Any], ...]
    quality: MarketDataQuality
    known_secrets: tuple[str, ...] = ()

    def feature(self, feature: str) -> pd.DataFrame:
        from research.aegis_research.market_data.loading import feature_from_ohlcv

        return feature_from_ohlcv(self, feature)

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)
