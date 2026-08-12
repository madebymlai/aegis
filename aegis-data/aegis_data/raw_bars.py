from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import CoverageInterval, ensure_coverage
from aegis_data.marking import DeclaredMarkingResolver, InstrumentMarking, RawBarTypeResolver
from aegis_data.provider import ProviderAnswer
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


class CatalogCoverageGapError(ValueError):
    """The Catalog cannot serve a requested covered window."""

    def __init__(
        self,
        subject: CatalogKey[Any],
        missing: Sequence[CoverageInterval],
        *,
        message: str,
    ) -> None:
        self.subject = subject
        self.missing = tuple(missing)
        super().__init__(message)


class GapFillProviderError(RuntimeError):
    """A provider failed environmentally while filling a Catalog gap."""


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
    clock_ns: Callable[[], int] = lambda: pd.Timestamp.now(tz="UTC").value
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
        markers = CoverageMarkerLedger(self.catalog)
        requested = CoverageInterval(interval.start_ns, interval.end_ns)
        for bar_type in marking.mark_bars:
            missing = markers.missing(CatalogKey.for_bar(bar_type), requested)
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
        return CoverageMarkerLedger(self.catalog).covered_through(
            CatalogKey.for_bar(bar_type)
        )

    def record_verified(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
        records: Sequence[Bar],
    ) -> None:
        """Record Bars and the ordinary verified interval they came from.

        This is the same storage command used by provider fills and subscribed
        capture. Empty ``records`` are still a verified-empty interval. Captured
        intraday fragments are consolidated into one daily file instead of
        accumulating one durable file per arriving Bar.
        """
        verified = CoverageInterval(interval.start_ns, interval.end_ns)
        selected = tuple(records)
        if any(record.bar_type != bar_type for record in selected):
            raise ValueError("verified Bars must all belong to the requested BarType")
        subject = CatalogKey.for_bar(bar_type)
        markers = CoverageMarkerLedger(self.catalog)
        self.catalog.replace(subject, interval, selected)
        markers.mark(
            subject,
            verified,
            checked_at_ns=self.clock_ns(),
            applicable=True,
        )
        day = _utc_day_interval(interval.end_ns)
        self.catalog.compact(
            subject,
            day,
            ensure_contiguous_files=False,
        )
        markers.consolidate(
            subject,
            CoverageInterval(day.start_ns, day.end_ns),
        )

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
        markers = CoverageMarkerLedger(self.catalog)
        provider = _bar_fetcher(self.provider, bar_type) if self.provider else None
        on_coverage_filled = None
        if self.definition_seeder is not None:
            definition_seeder = self.definition_seeder

            def seed_definition() -> None:
                definition_seeder(bar_type.instrument_id)

            on_coverage_filled = seed_definition
        requested = CoverageInterval(interval.start_ns, interval.end_ns)
        ensure_coverage(
            subject=str(bar_type),
            provider=provider,
            missing_intervals=lambda: markers.missing(subject, requested),
            commit=lambda verified, records: self.record_verified(
                bar_type,
                CatalogInterval(verified.start_ns, verified.end_ns),
                records,
            ),
            coverage_error=lambda missing: _coverage_gap(bar_type, missing),
            provider_boundary=gap_fill_boundary,
            finalize=lambda: self.catalog.compact(subject, interval),
            on_coverage_filled=on_coverage_filled,
        )

_CAUSE_SUMMARY_LIMIT = 200


def _utc_day_interval(timestamp_ns: int) -> CatalogInterval:
    day = pd.Timestamp(timestamp_ns, tz="UTC").normalize()
    return CatalogInterval(day.value, (day + pd.Timedelta(days=1)).value - 1)


@contextmanager
def gap_fill_boundary(subject: str) -> Iterator[None]:
    """Translate provider faults without changing coverage verdicts."""
    try:
        yield
    except CatalogCoverageGapError:
        raise
    except Exception as exc:
        raise GapFillProviderError(
            f"the gap-fill provider could not serve {subject}: "
            f"{type(exc).__name__}: {_cause_summary(exc)}"
        ) from exc


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


def _cause_summary(exc: Exception) -> str:
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    if len(first_line) <= _CAUSE_SUMMARY_LIMIT:
        return first_line
    return first_line[:_CAUSE_SUMMARY_LIMIT] + "…"


__all__ = [
    "CatalogCoverageGapError",
    "GapFillProviderError",
    "NautilusDataProviderPort",
    "RawBarWindow",
    "RawBars",
    "gap_fill_boundary",
]
