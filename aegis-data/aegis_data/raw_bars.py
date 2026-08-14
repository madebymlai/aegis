from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._ensure_coverage import (
    CatalogCoverageGapError,
    CoverageInterval,
    GapFillProviderError,
    ensure_coverage,
    gap_fill_boundary,
)
from aegis_data.marking import DeclaredMarkingResolver, InstrumentMarking, RawBarTypeResolver
from aegis_data.provider import ProviderAnswer
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


class NautilusDataProviderPort(Protocol):
    """Fetch Bars without owning persistence or coverage decisions."""

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[Bar]: ...


@dataclass(frozen=True)
class RawBarWindow:
    """One marking's native Bars plus its domain projections."""

    marking: InstrumentMarking
    by_type: Mapping[BarType, tuple[Bar, ...]]

    @property
    def bars(self) -> tuple[Bar, ...]:
        return tuple(
            bar
            for bar_type in self.marking.mark_bars
            for bar in self.by_type[bar_type]
        )

    @property
    def ohlcv(self) -> pd.DataFrame:
        return self.marking.ohlcv_frame(self.by_type)

    @property
    def quote_ohlcv(self) -> tuple[pd.DataFrame, pd.DataFrame] | None:
        return self.marking.quote_ohlcv_frames(self.by_type)


@dataclass(frozen=True)
class RawBars:
    """Own Raw Bar coverage commands and side-effect-free Catalog reads."""

    catalog: Catalog
    provider: NautilusDataProviderPort | None = None
    definition_seeder: Callable[[InstrumentId], None] | None = None
    resolver: RawBarTypeResolver = DeclaredMarkingResolver()

    def marking(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        """Resolve the Bar datasets and projection for one instrument."""
        return self.resolver.resolve(instrument_id, timeframe)

    def ensure(self, marking: InstrumentMarking, interval: CatalogInterval) -> None:
        """Ensure every Bar dataset required by *marking* is covered."""
        for bar_type in marking.mark_bars:
            self._ensure_bar_type(bar_type, interval)

    def covered(
        self,
        marking: InstrumentMarking,
        interval: CatalogInterval,
    ) -> RawBarWindow:
        """Read a covered window, failing loud on any gap without filling."""
        for bar_type in marking.mark_bars:
            missing = self.catalog.missing(CatalogKey.for_bar(bar_type), interval)
            if missing:
                raise _coverage_gap(bar_type, missing)
        return self._read(marking, interval)

    def stored(
        self,
        marking: InstrumentMarking,
        interval: CatalogInterval,
    ) -> RawBarWindow:
        """Read whatever is stored in a window, without a coverage gate."""
        return self._read(marking, interval)

    def covered_through(self, bar_type: BarType) -> int | None:
        """Return the latest verified endpoint for one Bar dataset."""
        return self.catalog.covered_through(CatalogKey.for_bar(bar_type))

    @property
    def can_fill(self) -> bool:
        """Whether a missing window can be obtained rather than only read."""
        return self.provider is not None

    def record_verified(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
        records: Sequence[Bar],
    ) -> None:
        """Record Bars and the ordinary verified interval they came from.

        This is the same storage command used by provider fills and subscribed
        capture. Empty ``records`` are still a verified-empty interval — the
        write records the window it answered for either way. Captured fragments
        are consolidated into one daily file instead of accumulating one
        durable file per arriving Bar.
        """
        selected = tuple(records)
        if any(record.bar_type != bar_type for record in selected):
            raise ValueError("verified Bars must all belong to the requested BarType")
        subject = CatalogKey.for_bar(bar_type)
        self.catalog.replace(subject, interval, selected)
        day_so_far = CatalogInterval(
            _utc_day_interval(interval.end_ns).start_ns,
            interval.end_ns,
        )
        self.catalog.compact(subject, day_so_far)

    def _read(
        self,
        marking: InstrumentMarking,
        interval: CatalogInterval,
    ) -> RawBarWindow:
        return RawBarWindow(
            marking,
            {
                bar_type: self.catalog.read(CatalogKey.for_bar(bar_type), interval)
                for bar_type in marking.mark_bars
            },
        )

    def _ensure_bar_type(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
    ) -> None:
        subject = CatalogKey.for_bar(bar_type)
        provider = _bar_fetcher(self.provider, bar_type) if self.provider else None

        def consolidate_and_seed() -> None:
            self.catalog.compact(subject, interval)
            if self.definition_seeder is not None:
                with gap_fill_boundary(str(bar_type)):
                    self.definition_seeder(bar_type.instrument_id)

        ensure_coverage(
            subject=str(bar_type),
            provider=provider,
            missing_intervals=lambda: list(self.catalog.missing(subject, interval)),
            commit=lambda verified, records: self.record_verified(
                bar_type,
                verified,
                records,
            ),
            coverage_error=lambda missing: _coverage_gap(bar_type, missing),
            on_filled=consolidate_and_seed,
        )


def _utc_day_interval(timestamp_ns: int) -> CatalogInterval:
    day = pd.Timestamp(timestamp_ns, tz="UTC").normalize()
    return CatalogInterval(day.value, (day + pd.Timedelta(days=1)).value - 1)


def _bar_fetcher(
    provider: NautilusDataProviderPort,
    bar_type: BarType,
) -> Callable[[pd.Timestamp, pd.Timestamp], ProviderAnswer[Bar]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> ProviderAnswer[Bar]:
        return provider.request_bars(bar_type, start=start, end=end)

    return fetch


def _coverage_gap(
    bar_type: BarType,
    intervals: Sequence[CoverageInterval],
) -> CatalogCoverageGapError:
    ranges = [
        f"{interval.start.isoformat()}..{interval.end.isoformat()}"
        for interval in intervals
    ]
    return CatalogCoverageGapError(
        CatalogKey.for_bar(bar_type),
        intervals,
        message=(
            f"catalog cannot serve {bar_type} for requested window; missing={ranges}"
        ),
    )


__all__ = [
    "CatalogCoverageGapError",
    "GapFillProviderError",
    "NautilusDataProviderPort",
    "RawBarWindow",
    "RawBars",
]
