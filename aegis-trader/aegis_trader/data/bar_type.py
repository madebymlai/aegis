"""Bar identity for the overlay.

The contract-timeframe -> Nautilus ``BarType`` mapping (LAST + EXTERNAL) and the
rebalance-period width live in ``aegis_data`` (ADR-0007): it is the shared lower
context both Aegis RD and the trader depend on, so the bar identity is single
sourced there and the two sides cannot desync.  This module re-exports the
helper and keeps only the *book-cadence policy* that is the trader's alone — all
commingled-book sleeves must agree on one rebalance period.
"""

from __future__ import annotations

from collections.abc import Iterable

from aegis_data.bar_type import (
    UnsupportedTimeframeError,
    raw_bar_type,
    timeframe_to_ns,
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


def resolve_book_timeframe(timeframes: Iterable[str]) -> str:
    """The single timeframe the commingled book runs on; all sleeves must agree,
    or fail closed (the overlay tracks one rebalance period)."""
    unique = tuple(dict.fromkeys(timeframes))
    if len(unique) != 1:
        raise MixedTimeframeError(unique)
    return unique[0]


__all__ = [
    "MixedTimeframeError",
    "UnsupportedTimeframeError",
    "raw_bar_type",
    "resolve_book_timeframe",
    "timeframe_to_ns",
]
