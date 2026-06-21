"""Coverage-aware cache for Databento Raw Futures Legs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from aegis_data.calendars import TradingCalendar
from aegis_data.chain import ContractFetcher, VolumeProbe
from aegis_data.store import (
    CoveredWindow,
    HistoricalStore,
    NATIVE_OHLCV_ARRAYS,
    RawFuturesLeg,
)

_DAILY_PROBE_TIMEFRAME = "1D"


class RawLegCacheConfigError(ValueError):
    """RawLegCache was constructed with an invalid configuration."""


class RawLegCacheDatasetError(RawLegCacheConfigError):
    """RawLegCache dataset is invalid."""


class RawLegCacheTimeframeError(RawLegCacheConfigError):
    """RawLegCache timeframe is invalid."""


class RawLegCacheArraysError(RawLegCacheConfigError):
    """RawLegCache arrays are invalid."""


@dataclass(frozen=True)
class LegPorts:
    """Fetch/probe callables bound through one raw-leg cache factory."""

    fetch: ContractFetcher
    probe: VolumeProbe


class RawLegCache:
    """Serve dated-contract leg windows from one coverage-aware raw-leg corpus."""

    def __init__(
        self,
        *,
        dataset: str,
        timeframe: str,
        fetch: ContractFetcher,
        arrays: Sequence[str] = NATIVE_OHLCV_ARRAYS,
        store_dir: Path | None = None,
        calendar: TradingCalendar | str = TradingCalendar.CONTINUOUS,
    ) -> None:
        if not dataset:
            raise RawLegCacheDatasetError("RawLegCache dataset must be a non-empty string")
        if not timeframe:
            raise RawLegCacheTimeframeError("RawLegCache timeframe must be a non-empty string")
        required_arrays = tuple(arrays)
        if not required_arrays:
            raise RawLegCacheArraysError("RawLegCache arrays must not be empty")
        self.dataset = dataset
        self.timeframe = timeframe
        self._fetch = fetch
        self.arrays = required_arrays
        self.store = HistoricalStore(store_dir) if store_dir is not None else HistoricalStore()
        self.calendar = calendar

    def fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch or read one dated-contract leg over inclusive ``[start, end]``."""
        leg = RawFuturesLeg(self.dataset, symbol)
        window = _inclusive_contract_window(
            self.timeframe,
            self.calendar,
            self.arrays,
            start,
            end,
        )
        for gap in self.store.leg_fetch_gaps(leg, window):
            self._fetch_gap(leg, window.narrowed_to(gap))
        return self.store.read_leg(leg, window)

    def _fetch_gap(self, leg: RawFuturesLeg, window: CoveredWindow) -> None:
        start = pd.Timestamp(window.start).date()
        end = _inclusive_window_end(window)
        self.store.merge_leg(
            leg,
            self._fetch(leg.symbol, start, end),
            window,
        )

    def contract_fetcher(self) -> ContractFetcher:
        """Return the cache bound to the existing chain fetcher protocol."""
        return self.fetch


def raw_leg_ports(
    *,
    dataset: str,
    timeframe: str,
    fetch: ContractFetcher,
    arrays: Sequence[str] = NATIVE_OHLCV_ARRAYS,
    store_dir: Path | None = None,
) -> LegPorts:
    """Build deliverable fetch and daily-volume probe ports from raw-leg caches."""
    required = _with_volume(arrays)
    deliverable = RawLegCache(
        dataset=dataset,
        timeframe=timeframe,
        fetch=fetch,
        arrays=required,
        store_dir=store_dir,
    )
    probe_timeframe = _daily_probe_timeframe(timeframe)
    probe_cache = (
        deliverable
        if probe_timeframe == timeframe
        else RawLegCache(
            dataset=dataset,
            timeframe=probe_timeframe,
            fetch=fetch,
            arrays=required,
            store_dir=store_dir,
        )
    )

    def probe(symbol: str, start: date, end: date) -> pd.Series:
        return probe_cache.fetch(symbol, start, end)["Volume"]

    return LegPorts(fetch=deliverable.fetch, probe=probe)


def _inclusive_contract_window(
    timeframe: str,
    calendar: TradingCalendar | str,
    arrays: Sequence[str],
    start: date,
    end: date,
) -> CoveredWindow:
    return CoveredWindow(
        timeframe=timeframe,
        calendar=calendar,
        start=start,
        end=pd.Timestamp(end) + pd.Timedelta(days=1),
        arrays=arrays,
    )


def _inclusive_window_end(window: CoveredWindow) -> date:
    return (pd.Timestamp(window.end) - pd.Timedelta(days=1)).date()


def _daily_probe_timeframe(timeframe: str) -> str:
    if pd.Timedelta(timeframe) == pd.Timedelta(days=1):
        return timeframe
    return _DAILY_PROBE_TIMEFRAME


def _with_volume(arrays: Sequence[str]) -> tuple[str, ...]:
    values = tuple(arrays)
    if any(array.lower() == "volume" for array in values):
        return values
    return (*values, "Volume")


__all__ = [
    "LegPorts",
    "RawLegCache",
    "RawLegCacheArraysError",
    "RawLegCacheConfigError",
    "RawLegCacheDatasetError",
    "RawLegCacheTimeframeError",
    "raw_leg_ports",
]
