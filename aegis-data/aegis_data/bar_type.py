"""The single home for turning a ``DataContract`` timeframe into the Nautilus
``BarType`` of the shared Catalog, and into a rebalance-period width.

Daily Raw Bars are ``EXTERNAL`` (ADR-0007): the Catalog is vendor-aggregated
OHLCV (IBKR historical) — finished bars with
no tick feed to build a multi-year daily series from — and live can only receive
IBKR's completed daily bar via an ``EXTERNAL`` subscription.  The price type is
a *declared* fact carried by the marking seam (``aegis_data.marking``), never
derived here: :func:`external_bar_type` builds the key for whatever price type
the resolved marking states (LAST / MID / BID / ASK), and :func:`raw_bar_type`
is the LAST-only shorthand for the undeclared default.

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
    """The ``LAST-EXTERNAL`` ``BarType`` for *instrument_id* at *timeframe*.

    Known IBKR exchange venues are canonicalized to their MIC venue before the
    Catalog key is built, matching the IBKR provider's MIC-pinned definitions and
    fetched bars.  LAST only — the undeclared default (ADR-0007 amendment); any
    other price type is a declared marking and keys via
    :func:`external_bar_type` (e.g. a cash-FX conversion leg's ``MID``).
    """
    return external_bar_type(instrument_id, timeframe, "LAST")


def external_bar_type(
    instrument_id: InstrumentId, timeframe: str, price_type: str
) -> BarType:
    """The Catalog ``EXTERNAL`` ``BarType`` at an explicit price type.

    The pure bar-type builder the marking resolver feeds (ADR-0007 amendment):
    the price type is decided by the resolved mark mode — LAST/MID bar-marked,
    BID+ASK for a quote-marked instrument — never re-derived by a consumer.
    """
    step, unit = _parse(timeframe)
    catalog_id = mic_canonical_instrument_id(instrument_id)
    return BarType.from_str(
        f"{catalog_id.value}-{step}-{unit}-{price_type}-EXTERNAL"
    )


def mic_canonical_instrument_id(instrument_id: InstrumentId) -> InstrumentId:
    """Rewrite a raw IBKR-exchange venue to its ISO MIC (``LSE`` -> ``XLON``).

    The IBKR instrument provider stores definitions and bars under the MIC venue, so a
    config that names the raw IB exchange must be canonicalized to the MIC before its id
    is used as a catalog key.  A venue that is already a MIC, or has no IB mapping
    (``LSEETF``, ``IDEALPRO``, ``ARCA``), is returned unchanged.
    """
    mic_venue = _mic_venue(instrument_id.venue.value)
    if mic_venue is None:
        return instrument_id
    return InstrumentId.from_str(f"{instrument_id.symbol.value}.{mic_venue}")


def _mic_venue(venue: str) -> str | None:
    from nautilus_trader.adapters.interactive_brokers.parsing.instruments import (
        exchange_to_mic_venue,
    )

    return exchange_to_mic_venue(venue)


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
    "external_bar_type",
    "mic_canonical_instrument_id",
    "raw_bar_type",
    "timeframe_to_ns",
]
