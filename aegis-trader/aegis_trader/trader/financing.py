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
from nautilus_trader.model.enums import AccountType, PositionSide
from nautilus_trader.model.objects import Currency, Money

from aegis_runtime import debit_interest
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
        net_cash_by_currency: dict[str, float] = {}
        currency_by_code: dict[str, Currency] = {}
        accounts = tuple(self.exchange.cache.accounts())
        for account in accounts:
            for balance in account.balances_total().values():
                currency = balance.currency
                currency_code = str(currency)
                net_cash_by_currency[currency_code] = (
                    net_cash_by_currency.get(currency_code, 0.0) + balance.as_double()
                )
                currency_by_code[currency_code] = currency
        if any(_account_type(account) == AccountType.MARGIN for account in accounts):
            # Nautilus margin balances exclude open-position principal; add it back so the
            # netted balance matches the broker-visible cash loan before debit interest.
            self._apply_margin_position_cash_impact(
                net_cash_by_currency,
                currency_by_code,
            )

        for currency_code, cash in net_cash_by_currency.items():
            rate = self._costs.margin_interest.annual_rate_for(currency_code)
            self._charge(debit_interest(cash, rate, float(days)), currency_by_code[currency_code])

    def _apply_margin_position_cash_impact(
        self,
        net_cash_by_currency: dict[str, float],
        currency_by_code: dict[str, Currency],
    ) -> None:
        for position in self.exchange.cache.positions_open():
            instrument = self.exchange.cache.instrument(position.instrument_id)
            currency = instrument.quote_currency
            currency_code = str(currency)
            principal = self._position_principal(position)
            if position.side == PositionSide.LONG:
                cash_impact = -principal
            elif position.side == PositionSide.SHORT:
                cash_impact = principal
            else:
                continue
            net_cash_by_currency[currency_code] = (
                net_cash_by_currency.get(currency_code, 0.0) + cash_impact
            )
            currency_by_code[currency_code] = currency

    def _charge_short_borrow(self, days: int) -> None:
        borrow_rate = self._costs.borrow.annual_rate
        if borrow_rate == 0.0:
            return
        for position in self.exchange.cache.positions_open():
            if position.side != PositionSide.SHORT:
                continue
            instrument = self.exchange.cache.instrument(position.instrument_id)
            short_market_value = self._position_market_value(position)
            self._charge(short_market_value * borrow_rate * days / _DAYS_PER_YEAR, instrument.quote_currency)

    def _position_principal(self, position) -> float:
        avg_px_open = getattr(position, "avg_px_open", None)
        if avg_px_open is not None:
            price = _as_float(avg_px_open)
            if price > 0.0:
                return position.quantity.as_double() * price
        return self._position_market_value(position)

    def _position_market_value(self, position) -> float:
        return position.quantity.as_double() * self._mark_price(position.instrument_id)

    def _mark_price(self, instrument_id) -> float:
        book = self.exchange.get_book(instrument_id)
        price = None
        if book is not None:
            price = book.midpoint() or book.best_bid_price() or book.best_ask_price()
        if price is None:  # pragma: no cover - backtest bars should leave an EOD mark
            raise RuntimeError(f"cannot accrue financing without mark for {instrument_id}")
        return float(price)

    def _charge(self, amount: float, currency: Currency) -> None:
        if amount <= 0.0:
            return
        self._totals[str(currency)] = self._totals.get(str(currency), 0.0) + amount
        self.exchange.adjust_account(Money(-amount, currency))


def build_financing_module(costs: CostModelConfig) -> FinancingModule | None:
    """Return the book-level financing module required by configured costs."""
    has_debit_interest = bool(costs.margin_interest.annual_debit_rates)
    has_borrow = costs.borrow.annual_rate > 0.0
    if not has_debit_interest and not has_borrow:
        return None
    return FinancingModule(costs)


def _account_type(account) -> AccountType | None:
    account_type = getattr(account, "type", None)
    if callable(account_type):
        return account_type()
    return account_type


def _as_float(value) -> float:
    if hasattr(value, "as_double"):
        return float(value.as_double())
    return float(value)
