from __future__ import annotations

from types import SimpleNamespace

import pytest
from aegis_data.distributions import Distribution
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Currency

from aegis_trader.trader.dividends import dividend_cash_adjustments

_INSTRUMENT_ID = InstrumentId.from_str("DIV.SIM")


class _Quantity:
    def __init__(self, value: float) -> None:
        self._value = value

    def as_double(self) -> float:
        return self._value


def _position(side: PositionSide, quantity: float = 10.0):
    return SimpleNamespace(
        instrument_id=_INSTRUMENT_ID,
        side=side,
        quantity=_Quantity(quantity),
    )


def test_dividend_cash_adjustments_credit_longs_and_charge_shorts() -> None:
    distribution = Distribution.from_ex_date(
        _INSTRUMENT_ID,
        "2024-01-03",
        amount=0.50,
        currency="USD",
    )
    adjustments = dividend_cash_adjustments(
        distribution,
        (
            _position(PositionSide.LONG, 10.0),
            _position(PositionSide.SHORT, 4.0),
        ),
    )

    assert [money.as_double() for money in adjustments] == pytest.approx([5.0, -2.0])
    assert [money.currency for money in adjustments] == [
        Currency.from_str("USD"),
        Currency.from_str("USD"),
    ]
