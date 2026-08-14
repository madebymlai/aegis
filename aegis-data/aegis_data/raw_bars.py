from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.marking import (
    DeclaredMarkingResolver,
    InstrumentMarking,
    RawBarTypeResolver,
)
from aegis_data.provider_errors import GapFillProviderError, gap_fill_boundary
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


class BarWarmerPort(Protocol):
    """Warm Bars while the Nautilus engine owns persistence and coverage."""

    def warm_bars(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
    ) -> bool: ...


@dataclass(frozen=True)
class RawBarWindow:
    """One marking's native Bars plus its domain projections."""

    marking: InstrumentMarking
    by_type: Mapping[BarType, tuple[Bar, ...]]

    @property
    def bars(self) -> tuple[Bar, ...]:
        return tuple(
            bar for bar_type in self.marking.mark_bars for bar in self.by_type[bar_type]
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
    provider: BarWarmerPort | None = None
    definition_seeder: Callable[[InstrumentId], None] | None = None
    resolver: RawBarTypeResolver = DeclaredMarkingResolver()

    def marking(self, instrument_id: InstrumentId, timeframe: str) -> InstrumentMarking:
        """Resolve the Bar datasets and projection for one instrument."""
        return self.resolver.resolve(instrument_id, timeframe)

    def ensure(self, marking: InstrumentMarking, interval: CatalogInterval) -> None:
        """Ensure every Bar dataset required by *marking* is covered."""
        for bar_type in marking.mark_bars:
            self._ensure_bar_type(bar_type, interval)

    def stored(
        self,
        marking: InstrumentMarking,
        interval: CatalogInterval,
    ) -> RawBarWindow:
        """Read what a window holds; absence is an empty answer, never an error.

        The only read there is. It once had a coverage-gated twin that raised on
        an unfilled window, but a window nothing can serve now returns empty
        (#96), which left the two indistinguishable.
        """
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
        if self.provider is None:
            return
        with gap_fill_boundary(str(bar_type)):
            fetched = self.provider.warm_bars(bar_type, interval)
        if fetched and self.definition_seeder is not None:
            with gap_fill_boundary(str(bar_type)):
                self.definition_seeder(bar_type.instrument_id)


def _utc_day_interval(timestamp_ns: int) -> CatalogInterval:
    day = pd.Timestamp(timestamp_ns, tz="UTC").normalize()
    return CatalogInterval(day.value, (day + pd.Timedelta(days=1)).value - 1)


__all__ = [
    "GapFillProviderError",
    "BarWarmerPort",
    "RawBarWindow",
    "RawBars",
]
