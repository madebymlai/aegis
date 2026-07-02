"""The Backtest Timeframe rule — the single bar timeframe a Commingled Book runs.

Every sleeve installed in one book is bound to an Execution Bundle that declares
its own contract timeframe; the overlay tracks a single rebalance period, so all
sleeves must agree on one.  A book whose sleeves declare mixed timeframes is a
closed failure (the ``BOOK_TIMEFRAME`` startup gate), not a multi-timeframe
simulation.

This is a pure book invariant over the sleeves' declared timeframes — it does
not touch bar identity, which is single sourced in ``aegis_data.bar_type``.
"""

from __future__ import annotations

from collections.abc import Iterable


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
    "resolve_book_timeframe",
]
