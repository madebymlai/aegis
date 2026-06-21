"""Pure interval ledger for Raw Futures Leg fetch bookkeeping."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from aegis_data.store_coverage import CoverageGap


@dataclass(frozen=True, order=True)
class FetchedInterval:
    """Covered half-open interval already requested from a provider."""

    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        start = _timestamp(self.start)
        end = _timestamp(self.end)
        if end <= start:
            raise ValueError(f"FetchedInterval end must be after start; got {start!r} -> {end!r}")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True)
class FetchLedger:
    """Coalesced fetched intervals for one Raw Futures Leg."""

    _intervals: tuple[FetchedInterval, ...]

    @classmethod
    def of(cls, intervals: Iterable[FetchedInterval]) -> FetchLedger:
        """Build a ledger with sorted, non-overlapping, non-adjacent intervals."""
        coalesced: list[FetchedInterval] = []
        for interval in sorted(intervals, key=lambda value: (value.start, value.end)):
            if coalesced and interval.start <= coalesced[-1].end:
                coalesced[-1] = FetchedInterval(
                    start=coalesced[-1].start,
                    end=max(coalesced[-1].end, interval.end),
                )
                continue
            coalesced.append(interval)
        return cls(tuple(coalesced))

    @property
    def intervals(self) -> tuple[FetchedInterval, ...]:
        """Coalesced intervals for store serialization."""
        return self._intervals

    def gaps(self, window: FetchedInterval) -> tuple[CoverageGap, ...]:
        """Return the parts of ``window`` not covered by fetched intervals."""
        gaps: list[CoverageGap] = []
        cursor = window.start
        for interval in self._intervals:
            if interval.end <= window.start:
                continue
            if interval.start >= window.end:
                break
            covered_start = max(interval.start, window.start)
            covered_end = min(interval.end, window.end)
            if covered_start > cursor:
                gaps.append(CoverageGap(start=cursor, end=covered_start))
            cursor = max(cursor, covered_end)
        if cursor < window.end:
            gaps.append(CoverageGap(start=cursor, end=window.end))
        return tuple(gaps)


def _timestamp(value: pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.tz_localize(None)


__all__ = ["FetchedInterval", "FetchLedger"]
