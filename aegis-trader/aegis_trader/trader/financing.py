"""Backtest financing carry module.

Applies simulated broker financing per advancing UTC calendar day: negative cash
balances pay debit interest, and short positions pay borrow.  Each accrual
charges the full span of calendar days elapsed since the last one, so a Fri→Mon
gap with no weekend bars still accrues three days of carry (IBKR-faithful).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.backtest.config import SimulationModuleConfig
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.objects import Currency, Money

from aegis_trader.domain.book_config import CostModelConfig

_DAYS_PER_YEAR = 360.0


@dataclass(frozen=True)
class FinancingCostTotals:
    """Diagnostic total costs charged by financing currency."""

    by_currency: dict[str, float]


class FinancingModule(SimulationModule):
    """Accrues debit interest and short borrow fees at end-of-day marks."""

    def __init__(self, costs: CostModelConfig) -> None:
        super().__init__(SimulationModuleConfig())
        self._costs = costs
        self._last_accrual_date: pd.Timestamp | None = None
        self._totals: dict[str, float] = {}

    def process(self, ts_now: int) -> None:
        days = self._elapsed_days(pd.Timestamp(ts_now, tz="UTC").normalize())
        if days <= 0:
            return
        self._charge_debit_interest(days)
        self._charge_short_borrow(days)

    def _elapsed_days(self, date: pd.Timestamp) -> int:
        """Calendar days since the last accrual (0 on the first observed date).

        Charging the elapsed span — not a flat one day per observed bar — makes a
        Fri→Mon gap accrue 3 days of carry, matching IBKR's calendar-day
        financing across non-trading days.  Same-date and out-of-order ticks
        return 0, so financing accrues exactly once per advancing calendar day.
        """
        if self._last_accrual_date is None:
            self._last_accrual_date = date
            return 0
        days = (date - self._last_accrual_date).days
        if days > 0:
            self._last_accrual_date = date
        return days

    def log_diagnostics(self, logger) -> None:  # pragma: no cover - Nautilus hook
        totals = ", ".join(f"{amount:.2f} {currency}" for currency, amount in sorted(self._totals.items()))
        logger.info(f"Financing costs (totals): {totals}")

    def reset(self) -> None:
        self._last_accrual_date = None
        self._totals = {}

    @property
    def totals(self) -> FinancingCostTotals:
        return FinancingCostTotals(dict(self._totals))

    def _charge_debit_interest(self, days: int) -> None:
        account = self.exchange.get_account()
        if account is None:
            return
        for balance in account.balances_total().values():
            cash = balance.as_double()
            if cash >= 0.0:
                continue
            rate = self._costs.margin_interest.annual_rate_for(str(balance.currency))
            self._charge(-cash * rate * days / _DAYS_PER_YEAR, balance.currency)

    def _charge_short_borrow(self, days: int) -> None:
        borrow_rate = self._costs.borrow.annual_rate
        if borrow_rate == 0.0:
            return
        for position in self.exchange.cache.positions_open():
            if position.side != PositionSide.SHORT:
                continue
            instrument = self.exchange.instruments[position.instrument_id]
            mark = self._mark_price(position.instrument_id)
            short_market_value = position.quantity.as_double() * mark
            self._charge(short_market_value * borrow_rate * days / _DAYS_PER_YEAR, instrument.quote_currency)

    def _mark_price(self, instrument_id) -> float:
        book = self.exchange.get_book(instrument_id)
        price = book.midpoint() or book.best_bid_price() or book.best_ask_price()
        if price is None:  # pragma: no cover - backtest bars should leave an EOD mark
            raise RuntimeError(f"cannot accrue financing without mark for {instrument_id}")
        return float(price)

    def _charge(self, amount: float, currency: Currency) -> None:
        if amount <= 0.0:
            return
        self._totals[str(currency)] = self._totals.get(str(currency), 0.0) + amount
        self.exchange.adjust_account(Money(-amount, currency))


def build_financing_modules(costs: CostModelConfig) -> list[SimulationModule]:
    """Return simulation modules required by the configured financing costs."""
    has_debit_interest = bool(costs.margin_interest.annual_debit_rates)
    has_borrow = costs.borrow.annual_rate > 0.0
    if not has_debit_interest and not has_borrow:
        return []
    return [FinancingModule(costs)]
