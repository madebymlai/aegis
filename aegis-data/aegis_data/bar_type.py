"""The single home for turning a ``DataContract`` timeframe into the Nautilus
``BarType`` of the shared corpus, and into a rebalance-period width.

Daily Raw Bars are ``EXTERNAL`` (ADR-0007): the corpus is vendor-aggregated
OHLCV (IBKR historical) — finished bars with
no tick feed to build a multi-year daily series from — and live can only receive
IBKR's completed daily bar via an ``EXTERNAL`` subscription.  The price type is
``LAST`` for tradeables but ``MID`` for cash FX, which has no trades print: IBKR
serves MIDPOINT/BID/ASK for IDEALPRO, not TRADES, so a ``LAST`` request fails (IB
error 162).

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
    """The ``EXTERNAL`` ``BarType`` for *instrument_id* at *timeframe*.

    ``LAST`` for tradeables, ``MID`` for cash FX (ADR-0007).  Deciding the price
    type here — a pure function of the id — keeps write and read on one identity:
    both the lazy-fill/write and the warm read build the bar type through this
    helper, so an FX pair always keys as ``…-MID-EXTERNAL`` and never desyncs.
    """
    step, unit = _parse(timeframe)
    return BarType.from_str(
        f"{instrument_id.value}-{step}-{unit}-{_price_type(instrument_id)}-EXTERNAL"
    )


def _price_type(instrument_id: InstrumentId) -> str:
    """``MID`` for cash FX, ``LAST`` for everything else.

    A cash-FX pair carries the FX tell in its symbol shape — ``BASE/QUOTE`` — which
    is known from the id alone, before the instrument definition is resolved (on a
    cold fill the definition is seeded only *after* the bars are fetched, so the
    asset class is not yet available at request time).  IBKR has no TRADES print for
    cash FX, so its raw bars are ``MID``; everything else is ``LAST``.
    """
    return "MID" if "/" in instrument_id.symbol.value else "LAST"


def continuous_bar_type(root_id: InstrumentId, timeframe: str) -> BarType:
    """The continuous-future target ``BarType`` for a synthetic root at *timeframe*.

    ``{root}.{venue}-{step}-{unit}-LAST-INTERNAL@{step}-{unit}-EXTERNAL``: an
    internally-aggregated target over the per-leg ``LAST-EXTERNAL`` source (same
    cadence — a 1:1 daily composite).  Nautilus requires the continuous target to be
    internally aggregated and materialises each segment's real leg bars into it.
    *root_id* is the **synthetic continuous root** (e.g. ``ES.XCME``), not a real
    contract; the real legs are named in the roll transitions.
    """
    step, unit = _parse(timeframe)
    return BarType.from_str(
        f"{root_id.value}-{step}-{unit}-LAST-INTERNAL@{step}-{unit}-EXTERNAL"
    )


def timeframe_to_ns(timeframe: str) -> int:
    """The rebalance-period width, in nanoseconds, for *timeframe*."""
    step, unit = _parse(timeframe)
    return step * _UNIT_NS[unit]


__all__ = [
    "UnsupportedTimeframeError",
    "continuous_bar_type",
    "raw_bar_type",
    "timeframe_to_ns",
]
