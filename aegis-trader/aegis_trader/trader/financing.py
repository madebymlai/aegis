"""Backtest financing carry module.

Applies simulated broker financing once per UTC date after venue settlement:
negative cash balances pay debit interest, and short positions pay borrow.
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
        self._processed_dates: set[pd.Timestamp] = set()
        self._totals: dict[str, float] = {}

    def process(self, ts_now: int) -> None:
        date = pd.Timestamp(ts_now, tz="UTC").normalize()
        if date in self._processed_dates:
            return
        self._processed_dates.add(date)
        self._charge_debit_interest()
        self._charge_short_borrow()

    def log_diagnostics(self, logger) -> None:  # pragma: no cover - Nautilus hook
        totals = ", ".join(f"{amount:.2f} {currency}" for currency, amount in sorted(self._totals.items()))
        logger.info(f"Financing costs (totals): {totals}")

    def reset(self) -> None:
        self._processed_dates = set()
        self._totals = {}

    @property
    def totals(self) -> FinancingCostTotals:
        return FinancingCostTotals(dict(self._totals))

    def _charge_debit_interest(self) -> None:
        account = self.exchange.get_account()
        if account is None:
            return
        for balance in account.balances_total().values():
            cash = balance.as_double()
            if cash >= 0.0:
                continue
            rate = self._costs.margin_interest.annual_rate_for(str(balance.currency))
            self._charge(-cash * rate / _DAYS_PER_YEAR, balance.currency)

    def _charge_short_borrow(self) -> None:
        borrow_rate = self._costs.borrow.annual_rate
        if borrow_rate == 0.0:
            return
        for position in self.exchange.cache.positions_open():
            if position.side != PositionSide.SHORT:
                continue
            instrument = self.exchange.instruments[position.instrument_id]
            mark = self._mark_price(position.instrument_id)
            short_market_value = position.quantity.as_double() * mark
            self._charge(short_market_value * borrow_rate / _DAYS_PER_YEAR, instrument.quote_currency)

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
