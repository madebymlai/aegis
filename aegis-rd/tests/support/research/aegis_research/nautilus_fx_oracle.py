"""The currency parity oracle: a minimal real Nautilus backtest.

A buy-and-hold of one foreign-quoted instrument is run through a real Nautilus
``BacktestEngine`` configured like the trader's (``base_currency=None`` MARGIN,
FX fed per bar via ``set_mark_xrate``). The per-bar base-currency marked value of
the position — ``net_exposure * get_mark_xrate(native, base)`` — is Nautilus' own
conversion, the oracle RD's vbt-side conversion must match.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency, Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

_FX_SIZE = Quantity.from_int(1_000_000)


def _bar_type(equity: Equity) -> BarType:
    return BarType.from_str(f"{equity.id}-1-DAY-LAST-EXTERNAL")


class _BuyAndHoldOracle(Strategy):
    """Buys a fixed quantity on the first bar, holds, and records the per-bar
    base-currency marked value of the position via Nautilus' own conversion."""

    def __init__(
        self,
        *,
        equity: Equity,
        fx_pair: CurrencyPair,
        base_currency: Currency,
        quantity: int,
    ) -> None:
        super().__init__(StrategyConfig())
        self._equity = equity
        self._fx_pair = fx_pair
        self._base = base_currency
        self._quantity = quantity
        self._bought = False
        self.base_value: dict[pd.Timestamp, float] = {}

    def on_start(self) -> None:
        self.subscribe_bars(_bar_type(self._equity))
        self.subscribe_quote_ticks(self._fx_pair.id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        instrument = self.cache.instrument(tick.instrument_id)
        if not isinstance(instrument, CurrencyPair):
            return
        mid = (tick.bid_price.as_double() + tick.ask_price.as_double()) / 2.0
        if mid > 0.0:
            self.cache.set_mark_xrate(instrument.base_currency, instrument.quote_currency, mid)

    def on_bar(self, bar: Bar) -> None:
        if not self._bought:
            order = self.order_factory.market(
                self._equity.id, OrderSide.BUY, Quantity.from_int(self._quantity)
            )
            self.submit_order(order)
            self._bought = True
        exposure = self.portfolio.net_exposure(self._equity.id)
        rate = self.cache.get_mark_xrate(self._equity.quote_currency, self._base)
        if exposure is None or rate is None or exposure.as_double() == 0.0:
            return
        self.base_value[pd.Timestamp(bar.ts_event, tz="UTC")] = exposure.as_double() * rate


def nautilus_base_value_curve(
    *,
    equity: Equity,
    fx_pair: CurrencyPair,
    native_close: pd.Series,
    fx_rate: pd.Series,
    quantity: int,
    base_currency: str = "EUR",
    starting_cash: float = 1_000_000.0,
) -> pd.Series:
    """Per-bar base-currency marked value of a held ``quantity`` of *equity*.

    *native_close* is the instrument's native price per bar; *fx_rate* is the
    declared FX pair's price per bar (``quote`` per 1 ``base``). Both are fed to a
    real engine; the returned series is Nautilus' base-currency valuation of the
    position on every bar it is open.
    """
    base = Currency.from_str(base_currency)
    native = equity.quote_currency
    venue = equity.id.venue

    engine = BacktestEngine(
        BacktestEngineConfig(trader_id="PARITY-001", logging=LoggingConfig(bypass_logging=True))
    )
    engine.add_venue(
        venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=None,
        starting_balances=[Money(starting_cash, base), Money(0, native)],
        allow_cash_borrowing=True,
    )
    engine.add_instrument(equity)
    engine.add_instrument(fx_pair)

    bar_type = _bar_type(equity)
    bars = [
        Bar(
            bar_type,
            Price.from_str(f"{close:.2f}"),
            Price.from_str(f"{close:.2f}"),
            Price.from_str(f"{close:.2f}"),
            Price.from_str(f"{close:.2f}"),
            Quantity.from_int(1_000),
            ts.value,
            ts.value,
        )
        for ts, close in native_close.items()
    ]
    precision = fx_pair.price_precision
    quotes = [
        QuoteTick(
            instrument_id=fx_pair.id,
            bid_price=Price(float(rate), precision),
            ask_price=Price(float(rate), precision),
            bid_size=_FX_SIZE,
            ask_size=_FX_SIZE,
            ts_event=ts.value,
            ts_init=ts.value,
        )
        for ts, rate in fx_rate.items()
    ]
    engine.add_data(quotes)
    engine.add_data(bars)
    engine.sort_data()

    strategy = _BuyAndHoldOracle(
        equity=equity, fx_pair=fx_pair, base_currency=base, quantity=quantity
    )
    engine.add_strategy(strategy)
    engine.run()
    curve = pd.Series(strategy.base_value).sort_index()
    engine.dispose()
    return curve
