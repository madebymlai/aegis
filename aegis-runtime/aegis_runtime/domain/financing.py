"""Shared financing arithmetic for research and trader backtests."""

from __future__ import annotations

from numba.extending import register_jitable


@register_jitable
def debit_interest(cash: float, rate: float, elapsed_days: float) -> float:
    """Charge debit interest on net negative cash balances.

    Positive balances earn nothing, negative balances accrue on a 360-day year,
    and elapsed calendar days are supplied by each engine. Rate and day
    validation belongs to the config layer.
    """
    return max(0.0, -cash) * rate * max(0.0, elapsed_days) / 360.0
