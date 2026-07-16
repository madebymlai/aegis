"""Backtest dividend cash module.

Credits listed-ETF ``Distribution`` cash events on their ex-date.  Long
positions receive the cash; short positions pay it.  Live needs no counterpart:
the broker books real dividend cash into the account.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from aegis_data.distributions import Distribution
from nautilus_trader.backtest.config import SimulationModuleConfig
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.objects import Currency, Money


@dataclass(frozen=True)
class DividendTotals:
    """Diagnostic net dividend cash booked by currency."""

    by_currency: dict[str, float]


class DividendModule(SimulationModule):
    """Books scheduled distribution cash once per ex-date.

    The exact-date match is sound for ANY bar cadence because the backtest
    injects every ``Distribution`` as an engine data event at its ex-date
    timestamp (``_add_distribution_data``), so ``process`` is guaranteed a
    tick on each ex-date even when no bar lands there (e.g. a weekly Book
    with a Wednesday ex-date) — pinned by the weekly distribution e2e.
    """

    def __init__(self, distributions: Sequence[Distribution]) -> None:
        super().__init__(SimulationModuleConfig())
        self._schedule = _schedule_by_ex_date(distributions)
        self._booked_dates: set[int] = set()
        self._totals: dict[str, float] = {}

    def process(self, ts_now: int) -> None:
        ex_date = pd.Timestamp(ts_now, tz="UTC").normalize().value
        if ex_date in self._booked_dates:
            return
        self._booked_dates.add(ex_date)
        for distribution in self._schedule.get(ex_date, ()):
            self._book_distribution(distribution)

    def log_diagnostics(self, logger) -> None:  # pragma: no cover - Nautilus hook
        totals = ", ".join(
            f"{amount:.2f} {currency}"
            for currency, amount in sorted(self._totals.items())
        )
        logger.info(f"Dividend cash (totals): {totals}")

    def reset(self) -> None:
        self._booked_dates = set()
        self._totals = {}

    @property
    def totals(self) -> DividendTotals:
        return DividendTotals(dict(self._totals))

    def _book_distribution(self, distribution: Distribution) -> None:
        for cash in dividend_cash_adjustments(
            distribution,
            self.exchange.cache.positions_open(),
        ):
            self._totals[distribution.currency] = (
                self._totals.get(distribution.currency, 0.0) + cash.as_double()
            )
            self.exchange.adjust_account(cash)


def build_dividend_modules(
    distributions: Sequence[Distribution],
) -> list[SimulationModule]:
    """Return simulation modules required by listed-ETF distribution cash."""
    if not distributions:
        return []
    return [DividendModule(distributions)]


def dividend_cash_adjustments(distribution: Distribution, positions) -> list[Money]:
    """Signed account cash adjustments for one distribution event."""
    currency = Currency.from_str(distribution.currency)
    adjustments: list[Money] = []
    for position in positions:
        if position.instrument_id != distribution.instrument_id:
            continue
        quantity = position.quantity.as_double()
        signed_quantity = -quantity if position.side == PositionSide.SHORT else quantity
        amount = signed_quantity * distribution.amount
        if amount != 0.0:
            adjustments.append(Money(amount, currency))
    return adjustments


def _schedule_by_ex_date(
    distributions: Sequence[Distribution],
) -> dict[int, tuple[Distribution, ...]]:
    grouped: dict[int, list[Distribution]] = {}
    for distribution in distributions:
        ex_date = pd.Timestamp(distribution.ts_event, tz="UTC").normalize().value
        grouped.setdefault(ex_date, []).append(distribution)
    return {key: tuple(value) for key, value in grouped.items()}


__all__ = [
    "DividendModule",
    "DividendTotals",
    "build_dividend_modules",
    "dividend_cash_adjustments",
]
