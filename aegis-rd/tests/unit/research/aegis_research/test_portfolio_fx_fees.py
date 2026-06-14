from __future__ import annotations

import pandas as pd
from pandas.testing import assert_series_equal

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.portfolios import (
    fx_adjusted_fees,
    simulate_single_book,
)


def test_foreign_legs_pay_the_conversion_cost_base_legs_do_not() -> None:
    fees = fx_adjusted_fees(
        symbols=["VOOL.DE", "SGLN.L"],
        currency_by_symbol={"VOOL.DE": "EUR", "SGLN.L": "USD"},
        base_currency="EUR",
        base_fee=0.0005,
        fx_conversion_cost=0.0003,
    )

    expected = pd.Series({"VOOL.DE": 0.0005, "SGLN.L": 0.0008})
    assert_series_equal(fees, expected)


def test_gbp_minor_unit_leg_is_foreign_and_pays_the_conversion_cost() -> None:
    fees = fx_adjusted_fees(
        symbols=["GBUS.L"],
        currency_by_symbol={"GBUS.L": "GBp"},
        base_currency="EUR",
        base_fee=0.0005,
        fx_conversion_cost=0.0003,
    )

    expected = pd.Series({"GBUS.L": 0.0008})
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
