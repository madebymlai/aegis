from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration.schema import OHLCV_ARRAYS, DataConfig

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
        return to_builtin(self)


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
        from research.aegis_research.market_data.panels import feature_from_ohlcv

        return feature_from_ohlcv(self, feature)

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)


@dataclass(frozen=True)
class MarketDataBundle:
    features: dict[str, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    native_data: Any | None = None
    loaded_features: tuple[str, ...] = ()
    feature_getter: Callable[[str], pd.DataFrame] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def feature(self, feature: str) -> pd.DataFrame:
        if self.loaded_features and feature not in self.loaded_features:
            raise ValueError(f"market data feature {feature!r} was not loaded for this run")
        panel = self.features.get(feature)
        if panel is not None:
            return panel
        if self.feature_getter is not None:
            return self.feature_getter(feature)
        raise ValueError(f"market data feature {feature!r} is not available")


def market_data_bundle(result: MarketDataResult) -> MarketDataBundle:
    result.assert_usable()
    return MarketDataBundle(
        metadata=result.metadata,
        native_data=result.native_data,
        loaded_features=tuple(result.metadata.get("loaded_arrays", ())),
        feature_getter=result.feature,
    )
