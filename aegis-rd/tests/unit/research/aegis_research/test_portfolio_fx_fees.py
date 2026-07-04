from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId
from pandas.testing import assert_series_equal

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.portfolios import (
    fx_adjusted_fees,
    simulate_single_book,
)


def test_foreign_legs_pay_the_conversion_cost_base_legs_do_not() -> None:
    vool = _id("VOOL.DE")
    sgln = _id("SGLN.L")
    fees = fx_adjusted_fees(
        instrument_ids=[vool, sgln],
        currency_by_instrument_id={vool: "EUR", sgln: "USD"},
        base_currency="EUR",
        base_fee=0.0005,
        fx_conversion_cost=0.0003,
    )

    expected = pd.Series({vool: 0.0005, sgln: 0.0008})
    assert_series_equal(fees, expected)


def test_gbp_minor_unit_leg_is_foreign_and_pays_the_conversion_cost() -> None:
    gbus = _id("GBUS.L")
    fees = fx_adjusted_fees(
        instrument_ids=[gbus],
        currency_by_instrument_id={gbus: "GBp"},
        base_currency="EUR",
        base_fee=0.0005,
        fx_conversion_cost=0.0003,
    )

    expected = pd.Series({gbus: 0.0008})
    assert_series_equal(fees, expected)


def test_per_symbol_fees_charge_each_leg_its_own_rate_in_simulation() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="D")
    close = pd.DataFrame({"A": 100.0, "B": 100.0}, index=index)
    # Enter both legs at bar 1; the terminal row is liquidated, so both trade.
    allocations = pd.DataFrame(
        {"A": [0.0, 0.5, 0.5, 0.5], "B": [0.0, 0.5, 0.5, 0.5]}, index=index
    )
    config = PortfolioConfig(gross_cap=1.0, direction="both", fees=0.0)

    cheap = simulate_single_book(
        close, allocations, config, fees_by_symbol=pd.Series({"A": 0.001, "B": 0.001})
    )
    pricey = simulate_single_book(
        close, allocations, config, fees_by_symbol=pd.Series({"A": 0.001, "B": 0.10})
    )

    # Only B's rate differs, so the pricier B leg must raise total fees paid.
    assert pricey.orders.fees.sum() > cheap.orders.fees.sum()


def test_fixed_fee_charges_a_flat_amount_on_every_order() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="D")
    close = pd.DataFrame({"A": 100.0}, index=index)
    # Enter A at bar 1; the terminal row is liquidated, so exactly two orders fill
    # (the entry and the close). same_close fills each target on its own bar so the
    # order count is deterministic.
    allocations = pd.DataFrame({"A": [0.0, 1.0, 1.0, 1.0]}, index=index)
    free = PortfolioConfig(
        gross_cap=1.0, direction="longonly", fees=0.0, slippage=0.0, fill_timing="same_close"
    )
    charged = PortfolioConfig(
        gross_cap=1.0, direction="longonly", fees=0.0, slippage=0.0,
        fill_timing="same_close", fixed_fee=2.0,
    )

    without = simulate_single_book(close, allocations, free)
    with_fixed = simulate_single_book(close, allocations, charged)

    # With proportional fees off, every order's fee is exactly the flat 2.0 -
    # charged per order, not per traded value - while the free book pays nothing.
    assert without.orders.fees.sum() == pytest.approx(0.0)
    assert len(with_fixed.orders.fees) >= 1
    assert with_fixed.orders.fees.min() == pytest.approx(2.0)
    assert with_fixed.orders.fees.max() == pytest.approx(2.0)


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)
