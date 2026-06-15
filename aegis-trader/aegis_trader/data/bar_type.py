"""Single source of truth: a ``DataContract`` timeframe -> the Nautilus
``BarType`` the overlay both loads (backtest LOAD side) and subscribes
(strategy SUBSCRIBE side).  The overlay's invariant LAST + EXTERNAL parts are
applied here, so the two sides can never desync on the bar type.

The timeframe is the pandas/vbt offset-alias spelling Aegis RD uses (e.g. ``1D``,
``1H``, ``15min``, ``1W``).  A timeframe the overlay cannot express as a Nautilus
bar step fails closed, rather than silently mis-loading or mis-subscribing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from nautilus_trader.model.data import BarType

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
    """A contract timeframe the overlay cannot express as a Nautilus bar step."""

    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe
        super().__init__(
            f"unsupported contract timeframe {timeframe!r}: expected a positive "
            f"count of a fixed unit (e.g. 1D, 1H, 15min, 1W)"
        )


class MixedTimeframeError(ValueError):
    """A commingled book whose sleeves declare more than one timeframe — the
    overlay tracks a single rebalance period, so all sleeves must agree."""

    def __init__(self, timeframes: tuple[str, ...]) -> None:
        self.timeframes = timeframes
        super().__init__(
            f"book sleeves declare mixed timeframes {list(timeframes)}; all "
            f"sleeves must share one timeframe"
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


def bar_type(instrument_id_value: str, timeframe: str) -> BarType:
    """The LAST-EXTERNAL ``BarType`` for *instrument_id_value* at *timeframe*."""
    step, unit = _parse(timeframe)
    return BarType.from_str(f"{instrument_id_value}-{step}-{unit}-LAST-EXTERNAL")


def timeframe_to_ns(timeframe: str) -> int:
    """The rebalance period width, in nanoseconds, for *timeframe*."""
    step, unit = _parse(timeframe)
    return step * _UNIT_NS[unit]


def resolve_book_timeframe(timeframes: Iterable[str]) -> str:
    """The single timeframe the commingled book runs on; all sleeves must agree,
    or fail closed (the overlay tracks one rebalance period)."""
    unique = tuple(dict.fromkeys(timeframes))
    if len(unique) != 1:
        raise MixedTimeframeError(unique)
    return unique[0]
