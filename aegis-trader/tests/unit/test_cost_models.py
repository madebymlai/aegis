"""Unit tests for Nautilus simulated cost models — no ibapi."""

from __future__ import annotations

import sys

import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_trader.domain.book_config import CostModelConfig
from aegis_trader.trader.costs import IbkrEquityFeeModel, build_simulated_fill_model


def _equity(currency: str = "EUR"):
    instrument_id = InstrumentId.from_str(f"TEST_{currency}.SIM")
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str(currency),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _commission_amount(
    model: IbkrEquityFeeModel,
    *,
    quantity: int,
    price: str,
    currency: str = "EUR",
) -> float:
    commission = model.get_commission(
        order=None,
        fill_qty=Quantity.from_int(quantity),
        fill_px=Price.from_str(price),
        instrument=_equity(currency),
    )
    assert commission.currency.code == currency
    return commission.as_double()


def test_base_currency_commission_uses_per_share_floor_and_cap():
    per_share_model = IbkrEquityFeeModel(
        CostModelConfig(
            per_share_commission=0.01,
            min_commission_per_order=1.0,
            max_commission_pct=0.10,
        ),
    )
    assert _commission_amount(per_share_model, quantity=200, price="50.00") == pytest.approx(2.0)
    assert _commission_amount(per_share_model, quantity=10, price="50.00") == pytest.approx(1.0)

    capped_model = IbkrEquityFeeModel(
        CostModelConfig(
            per_share_commission=2.0,
            min_commission_per_order=1.0,
            max_commission_pct=0.01,
        ),
    )
    assert _commission_amount(capped_model, quantity=100, price="50.00") == pytest.approx(50.0)


def test_per_value_commission_floors_small_european_orders():
    model = IbkrEquityFeeModel(
        CostModelConfig(commission_pct=0.0005, min_commission_per_order=1.25),
    )

    # 0.05% of EUR 250 = EUR 0.125 -> the EUR 1.25 per-order floor binds.
    assert _commission_amount(model, quantity=5, price="50.00") == pytest.approx(1.25)
    # 0.05% of EUR 5,000 = EUR 2.50 -> the percentage charge binds.
    assert _commission_amount(model, quantity=100, price="50.00") == pytest.approx(2.50)


def test_commission_is_currency_agnostic():
    costs = CostModelConfig(
        per_share_commission=0.01,
        min_commission_per_order=1.0,
        max_commission_pct=0.10,
    )
    model = IbkrEquityFeeModel(costs)

    base = _commission_amount(model, quantity=200, price="50.00", currency="EUR")
    foreign = _commission_amount(model, quantity=200, price="50.00", currency="GBP")

    assert foreign == pytest.approx(base)


def test_zero_cost_config_yields_zero_commission():
    model = IbkrEquityFeeModel(CostModelConfig.zero())

    assert _commission_amount(model, quantity=200, price="50.00", currency="EUR") == 0.0
    assert _commission_amount(model, quantity=200, price="50.00", currency="GBP") == 0.0


def test_fill_model_carries_configured_probability_and_seed():
    fill_model = build_simulated_fill_model(
        CostModelConfig(slippage_probability=0.25, slippage_seed=42)
    )

    assert fill_model.prob_slippage == pytest.approx(0.25)
    assert fill_model.prob_fill_on_limit == pytest.approx(1.0)
    assert fill_model.random_seed == 42


def test_cost_models_do_not_import_ibapi():
    assert "ibapi" not in sys.modules
