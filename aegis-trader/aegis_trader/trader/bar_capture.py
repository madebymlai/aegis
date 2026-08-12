"""Capture subscribed Bar streams into ordinary Raw Bar coverage."""

from __future__ import annotations

from dataclasses import dataclass, field

from nautilus_trader.model.data import Bar, BarType

from aegis_data.raw_bars import RawBars
from aegis_data.storage import CatalogInterval


class LateCapturedBarError(ValueError):
    """A Bar arrived after its event time was already verified as silent."""


@dataclass
class BarCapture:
    """Batch subscribed Bars and verify each stream through the session clock."""

    raw_bars: RawBars
    _frontier_by_type: dict[BarType, int] = field(default_factory=dict)
    _pending_by_type: dict[BarType, list[Bar]] = field(default_factory=dict)

    def subscribe(self, bar_type: BarType, *, at_ns: int) -> None:
        """Begin verification at subscription time without healing an older gap."""
        if bar_type in self._frontier_by_type:
            return
        covered_through = self.raw_bars.covered_through(bar_type)
        self._frontier_by_type[bar_type] = max(
            covered_through if covered_through is not None else at_ns - 1,
            at_ns - 1,
        )
        self._pending_by_type[bar_type] = []

    def unsubscribe(self, bar_type: BarType, *, at_ns: int) -> None:
        """Verify through unsubscription and stop accepting the stream."""
        if bar_type not in self._frontier_by_type:
            return
        self._verify_type(bar_type, self._safe_clock_frontier(bar_type, at_ns))
        del self._frontier_by_type[bar_type]
        del self._pending_by_type[bar_type]

    def observe(self, bar: Bar) -> None:
        """Buffer an arriving Bar only when its stream is subscribed."""
        pending = self._pending_by_type.get(bar.bar_type)
        if pending is not None:
            if bar.ts_event <= self._frontier_by_type[bar.bar_type]:
                raise LateCapturedBarError(
                    f"{bar.bar_type} delivered {bar.ts_event} after coverage reached "
                    f"{self._frontier_by_type[bar.bar_type]}"
                )
            pending.append(bar)

    def verify_through(self, timestamp_ns: int) -> None:
        """Record every subscribed stream, including verified-empty silence."""
        for bar_type in tuple(self._frontier_by_type):
            self._verify_type(bar_type, timestamp_ns)

    def verify_clock(self, timestamp_ns: int) -> None:
        """Flush batches only through each cadence's completed clock frontier."""
        for bar_type in tuple(self._frontier_by_type):
            self._verify_type(
                bar_type,
                self._safe_clock_frontier(bar_type, timestamp_ns),
            )

    def _safe_clock_frontier(self, bar_type: BarType, timestamp_ns: int) -> int:
        pending = self._pending_by_type[bar_type]
        latest_observation = max(
            (bar.ts_event for bar in pending),
            default=timestamp_ns - int(bar_type.spec.timedelta.value),
        )
        return max(
            timestamp_ns - int(bar_type.spec.timedelta.value),
            latest_observation,
        )

    def _verify_type(self, bar_type: BarType, timestamp_ns: int) -> None:
        frontier = self._frontier_by_type[bar_type]
        if timestamp_ns <= frontier:
            return
        pending = self._pending_by_type[bar_type]
        records = tuple(
            bar for bar in pending if frontier < bar.ts_event <= timestamp_ns
        )
        self.raw_bars.record_verified(
            bar_type,
            CatalogInterval(frontier + 1, timestamp_ns),
            records,
        )
        self._pending_by_type[bar_type] = [
            bar for bar in pending if bar.ts_event > timestamp_ns
        ]
        self._frontier_by_type[bar_type] = timestamp_ns


__all__ = ["BarCapture", "LateCapturedBarError"]
