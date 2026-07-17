from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pandas as pd
import pytest
from nautilus_trader.model.enums import AccountType, PositionSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency, Money

from aegis_trader.backtest import _add_venues
from aegis_trader.domain.book_config import (
    BookConfig,
    BorrowConfig,
    CostModelConfig,
    MarginInterestConfig,
    SleeveConfig,
)
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.financing import FinancingModule
from tests.support.factories import assemble_test_book, make_bundle

_SLEEVE = SleeveName("trend")
_SHORT_ID = InstrumentId.from_str("SHORT.XNYS")


class _Account:
    def __init__(
        self,
        balances: dict[str, float],
        *,
        account_type: AccountType = AccountType.CASH,
    ) -> None:
        self._balances = balances
        self.type = account_type

    def balances_total(self) -> dict[str, Money]:
        return {
            currency: Money(amount, Currency.from_str(currency))
            for currency, amount in self._balances.items()
        }


class _Quantity:
    def __init__(self, value: float) -> None:
        self._value = value

    def as_double(self) -> float:
        return self._value


class _Book:
    def __init__(self, midpoint: float) -> None:
        self._midpoint = midpoint

    def midpoint(self) -> float:
        return self._midpoint

    def best_bid_price(self) -> None:
        return None

    def best_ask_price(self) -> None:
        return None


class _Cache:
    def __init__(
        self,
        accounts: tuple[_Account, ...],
        *,
        positions: tuple[object, ...] = (),
        instruments: dict[InstrumentId, object] | None = None,
    ) -> None:
        self._accounts = accounts
        self._positions = positions
        self._instruments = instruments or {}

    def accounts(self) -> tuple[_Account, ...]:
        return self._accounts

    def positions_open(self) -> tuple[object, ...]:
        return self._positions

    def instrument(self, instrument_id: InstrumentId) -> object:
        return self._instruments[instrument_id]


class _Exchange:
    def __init__(
        self,
        accounts: tuple[_Account, ...],
        *,
        own_account: _Account | None = None,
        positions: tuple[object, ...] = (),
        instruments: dict[InstrumentId, object] | None = None,
        per_venue_instruments: dict[InstrumentId, object] | None = None,
        mark: float | None = 1.0,
    ) -> None:
        self.cache = _Cache(accounts, positions=positions, instruments=instruments)
        self.instruments = per_venue_instruments or {}
        self._own_account = own_account or accounts[0]
        self._mark = mark
        self.adjustments: list[Money] = []

    def get_account(self) -> _Account:
        return self._own_account

    def get_book(self, _instrument_id: InstrumentId) -> _Book | None:
        if self._mark is None:
            return None
        return _Book(self._mark)

    def adjust_account(self, money: Money) -> None:
        self.adjustments.append(money)


class _TestFinancingModule(FinancingModule):
    def __init__(self, costs: CostModelConfig, exchange: _Exchange) -> None:
        super().__init__(costs)
        self._test_exchange = exchange

    @property
    def exchange(self) -> _Exchange:
        return self._test_exchange


class _Engine:
    def __init__(self) -> None:
        self.venues: list[dict[str, object]] = []

    def add_venue(self, venue, **kwargs) -> None:
        self.venues.append({"venue": venue, **kwargs})


def _ts(date: str) -> int:
    return pd.Timestamp(date, tz="UTC").value


def _costs(
    *,
    margin_rates: tuple[tuple[str, float], ...] = (),
    borrow_rate: float = 0.0,
) -> CostModelConfig:
    return CostModelConfig(
        margin_interest=MarginInterestConfig(margin_rates),
        borrow=BorrowConfig(borrow_rate),
    )


def _module(costs: CostModelConfig, exchange: _Exchange) -> _TestFinancingModule:
    return _TestFinancingModule(costs, exchange)


def _charged_amounts(exchange: _Exchange) -> list[float]:
    return [money.as_double() for money in exchange.adjustments]


def test_margin_interest_nets_cash_across_all_accounts() -> None:
    rate = 0.036
    accounts = (
        _Account({"EUR": 1_000_000.0}),
        _Account({"EUR": -1_750_000.0}),
    )
    exchange = _Exchange(accounts, own_account=accounts[0])
    module = _module(_costs(margin_rates=(("EUR", rate),)), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    expected = 225.0
    assert _charged_amounts(exchange) == pytest.approx([-expected])
    assert exchange.adjustments[0].currency == Currency.from_str("EUR")
    assert module.totals.by_currency == pytest.approx({"EUR": expected})


def test_margin_interest_does_not_net_across_currencies() -> None:
    rate = 0.036
    accounts = (
        _Account({"EUR": -100_000.0}),
        _Account({"USD": 1_000_000.0}),
    )
    exchange = _Exchange(accounts)
    module = _module(_costs(margin_rates=(("EUR", rate), ("USD", rate))), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    expected = 30.0
    assert _charged_amounts(exchange) == pytest.approx([-expected])
    assert exchange.adjustments[0].currency == Currency.from_str("EUR")


def test_margin_interest_accrues_only_on_advancing_calendar_days() -> None:
    accounts = (_Account({"EUR": -100_000.0}),)
    exchange = _Exchange(accounts)
    module = _module(_costs(margin_rates=(("EUR", 0.036),)), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))
    module.process(_ts("2024-01-08"))
    module.process(_ts("2024-01-04"))

    assert len(exchange.adjustments) == 1


def test_net_positive_currency_charges_no_interest() -> None:
    accounts = (
        _Account({"EUR": 100_000.0}),
        _Account({"EUR": -50_000.0}),
    )
    exchange = _Exchange(accounts)
    module = _module(_costs(margin_rates=(("EUR", 0.036),)), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    assert exchange.adjustments == []
    assert module.totals.by_currency == {}


def test_margin_account_debit_interest_infers_cash_loan_from_long_exposure() -> None:
    rate = 0.036
    position = SimpleNamespace(
        instrument_id=_SHORT_ID,
        side=PositionSide.LONG,
        quantity=_Quantity(15_000.0),
    )
    instrument = SimpleNamespace(quote_currency=Currency.from_str("EUR"))
    exchange = _Exchange(
        (_Account({"EUR": 1_000_000.0}, account_type=AccountType.MARGIN),),
        positions=(position,),
        instruments={_SHORT_ID: instrument},
        mark=100.0,
    )
    module = _module(_costs(margin_rates=(("EUR", rate),)), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    expected = 150.0
    assert _charged_amounts(exchange) == pytest.approx([-expected])
    assert module.totals.by_currency == pytest.approx({"EUR": expected})


def test_margin_account_cash_loan_uses_position_principal_when_no_book_mark() -> None:
    rate = 0.036
    position = SimpleNamespace(
        instrument_id=_SHORT_ID,
        side=PositionSide.LONG,
        quantity=_Quantity(15_000.0),
        avg_px_open=100.0,
    )
    instrument = SimpleNamespace(quote_currency=Currency.from_str("EUR"))
    exchange = _Exchange(
        (_Account({"EUR": 1_000_000.0}, account_type=AccountType.MARGIN),),
        positions=(position,),
        instruments={_SHORT_ID: instrument},
        mark=None,
    )
    module = _module(_costs(margin_rates=(("EUR", rate),)), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    expected = 150.0
    assert _charged_amounts(exchange) == pytest.approx([-expected])
    assert module.totals.by_currency == pytest.approx({"EUR": expected})


def test_short_borrow_resolves_instrument_through_shared_cache_once() -> None:
    position = SimpleNamespace(
        instrument_id=_SHORT_ID,
        side=PositionSide.SHORT,
        quantity=_Quantity(100.0),
    )
    instrument = SimpleNamespace(quote_currency=Currency.from_str("USD"))
    exchange = _Exchange(
        (_Account({"USD": 0.0}),),
        positions=(position,),
        instruments={_SHORT_ID: instrument},
        per_venue_instruments={},
        mark=20.0,
    )
    module = _module(_costs(borrow_rate=0.005), exchange)

    module.process(_ts("2024-01-05"))
    module.process(_ts("2024-01-08"))

    expected = 0.08333333333333333
    assert _charged_amounts(exchange) == pytest.approx([-0.08])
    assert exchange.adjustments[0].currency == Currency.from_str("USD")
    assert module.totals.by_currency == pytest.approx({"USD": expected})


def test_financing_module_attaches_once_to_starting_balance_venue_with_all_cost_currencies() -> None:
    class _Instrument:
        def __init__(self, instrument_id: str) -> None:
            self.id = InstrumentId.from_str(instrument_id)
            self.quote_currency = Currency.from_str("EUR")

    engine = _Engine()
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_SLEEVE,
                wheel_filename="trend.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
        costs=_costs(margin_rates=(("EUR", 0.0324), ("USD", 0.0513))),
    )
    assembled = assemble_test_book(
        book,
        {"trend.whl": make_bundle(direction="longonly")},
    )

    _add_venues(
        engine,
        book=assembled,
        instruments=(_Instrument("AAA.XMIL"), _Instrument("BBB.XNYS")),
        distributions=(),
        starting_cash=1_000_000.0,
    )

    first_modules = cast(list[object], engine.venues[0]["modules"])
    second_modules = cast(list[object], engine.venues[1]["modules"])
    assert sum(isinstance(module, FinancingModule) for module in first_modules) == 1
    assert all(not isinstance(module, FinancingModule) for module in second_modules)
    assert {
        balance.currency.code
        for balance in cast(list[Money], engine.venues[0]["starting_balances"])
    } == {"EUR", "USD"}
