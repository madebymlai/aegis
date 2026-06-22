"""The single home for turning a ``DataContract`` timeframe into the Nautilus
``BarType`` of the shared corpus, and into a rebalance-period width.

Daily Raw Bars are ``LAST-EXTERNAL`` (ADR-0007): the corpus is vendor-aggregated
OHLCV (IBKR historical, the future Databento futures seed) — finished bars with
no tick feed to build a multi-year daily series from — and live can only receive
IBKR's completed daily bar via an ``EXTERNAL`` subscription.

This is the lower, shared context both Aegis RD and Aegis Trader depend on, so
the helper lives here and neither side re-derives the bar identity (the r8b
desync vector).  The catalog stringifies the ``BarType`` only at the Nautilus
query/identifier boundary.

The timeframe is the pandas/vbt offset-alias spelling Aegis RD uses (e.g. ``1D``,
``1H``, ``15min``, ``1W``).  A timeframe that cannot be expressed as a Nautilus
bar step fails closed rather than silently mis-loading or mis-subscribing.
"""

from __future__ import annotations

import re

from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

# pandas offset-alias unit (lowercased) -> Nautilus bar aggregation.  Month is
# intentionally absent: it is not a fixed duration, so it has no period width.
_NAUTILUS_UNIT = {
    "s": "SECOND", "sec": "SECOND", "second": "SECOND", "seconds": "SECOND",
    "min": "MINUTE", "t": "MINUTE", "minute": "MINUTE", "minutes": "MINUTE",
    "h": "HOUR", "hour": "HOUR", "hours": "HOUR",
    "d": "DAY", "day": "DAY", "days": "DAY",
    "w": "WEEK", "week": "WEEK", "weeks": "WEEK",
}
_UNIT_NS = {
    "SECOND": 1_000_000_000,
    "MINUTE": 60_000_000_000,
    "HOUR": 3_600_000_000_000,
    "DAY": 86_400_000_000_000,
    "WEEK": 604_800_000_000_000,
}
_TIMEFRAME = re.compile(r"\s*(\d+)\s*([A-Za-z]+)\s*")


class UnsupportedTimeframeError(ValueError):
    """A contract timeframe that cannot be expressed as a Nautilus bar step."""

    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe
        super().__init__(
            f"unsupported contract timeframe {timeframe!r}: expected a positive "
            f"count of a fixed unit (e.g. 1D, 1H, 15min, 1W)"
        )


def _parse(timeframe: str) -> tuple[int, str]:
    """``(step, nautilus_unit)`` for *timeframe*, or fail closed."""
    match = _TIMEFRAME.fullmatch(timeframe)
    if match is None:
        raise UnsupportedTimeframeError(timeframe)
    step = int(match.group(1))
    unit = _NAUTILUS_UNIT.get(match.group(2).lower())
    if unit is None or step < 1:
        raise UnsupportedTimeframeError(timeframe)
    return step, unit


def raw_bar_type(instrument_id: InstrumentId, timeframe: str) -> BarType:
    """The ``LAST-EXTERNAL`` ``BarType`` for *instrument_id* at *timeframe*."""
    step, unit = _parse(timeframe)
    return BarType.from_str(f"{instrument_id.value}-{step}-{unit}-LAST-EXTERNAL")


def timeframe_to_ns(timeframe: str) -> int:
    """The rebalance-period width, in nanoseconds, for *timeframe*."""
    step, unit = _parse(timeframe)
    return step * _UNIT_NS[unit]


__all__ = [
    "UnsupportedTimeframeError",
    "raw_bar_type",
    "timeframe_to_ns",
]
