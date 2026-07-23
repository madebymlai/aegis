from __future__ import annotations

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.portfolio_simulation._simulation import (
    simulate_portfolio_batch,
)


def _order_sizes_for_initial_cash(
    initial_cash: float,
    *,
    size_increment: float = 1.0,
    multiplier: float = 1.0,
) -> tuple[float, ...]:
    instrument_id = InstrumentId.from_str("WHOLE.XNAS")
    index = pd.date_range("2026-01-01", periods=3)
    close = pd.DataFrame({instrument_id: 100.0}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [("candidate", instrument_id)],
        names=["candidate", "symbol"],
    )
    allocations = pd.DataFrame(
        [[1.0], [1.0], [np.nan]],
        index=index,
        columns=columns,
    )
    config = PortfolioConfig(
        direction="longonly",
        init_cash=initial_cash,
        fees=0.0,
        slippage=0.0,
        fixed_fee=0.0,
        margin_interest_rate=0.0,
    )
    book = ResolvedBook(
        config,
        size_increment_by_instrument={instrument_id: size_increment},
        multiplier_by_instrument={instrument_id: multiplier},
    )

    portfolio = simulate_portfolio_batch(close, allocations, book, periods_per_year=252)

    return tuple(portfolio.orders.records_readable["Size"])


def test_quantity_above_half_an_increment_rounds_to_nearest() -> None:
    order_sizes = _order_sizes_for_initial_cash(51.0)

    assert order_sizes == (1.0,)


def test_half_of_first_increment_rounds_to_even_zero() -> None:
    order_sizes = _order_sizes_for_initial_cash(50.0)

    assert order_sizes == ()


def test_one_and_a_half_increments_rounds_to_even_two() -> None:
    order_sizes = _order_sizes_for_initial_cash(150.0)

    assert order_sizes == (2.0,)


def test_one_point_nine_increments_rounds_to_nearest_two() -> None:
    order_sizes = _order_sizes_for_initial_cash(190.0)

    assert order_sizes == (2.0,)


def test_two_and_a_half_increments_rounds_to_even_two() -> None:
    order_sizes = _order_sizes_for_initial_cash(250.0)

    assert order_sizes == (2.0,)


def test_fractional_increment_rounds_to_nearest_multiple() -> None:
    order_sizes = _order_sizes_for_initial_cash(113.0, size_increment=0.25)

    assert order_sizes == (1.25,)


def test_large_increment_rounds_to_nearest_multiple() -> None:
    order_sizes = _order_sizes_for_initial_cash(15_000.0, size_increment=100.0)

    assert order_sizes == (200.0,)


def test_contract_multiplier_sizes_target_in_contracts() -> None:
    order_sizes = _order_sizes_for_initial_cash(5_000.0, multiplier=50.0)

    assert order_sizes == (1.0,)


def test_negative_rebalance_delta_rounds_to_nearest_multiple() -> None:
    instrument_id = InstrumentId.from_str("WHOLE.XNAS")
    index = pd.date_range("2026-01-01", periods=3)
    close = pd.DataFrame({instrument_id: 100.0}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [("candidate", instrument_id)],
        names=["candidate", "symbol"],
    )
    allocations = pd.DataFrame(
        [[1.0], [0.05], [np.nan]],
        index=index,
        columns=columns,
    )
    config = PortfolioConfig(
        direction="longonly",
        init_cash=200.0,
        fees=0.0,
        slippage=0.0,
        fixed_fee=0.0,
        margin_interest_rate=0.0,
        fill_timing="same_close",
    )
    book = ResolvedBook(
        config,
        size_increment_by_instrument={instrument_id: 1.0},
    )

    portfolio = simulate_portfolio_batch(close, allocations, book, periods_per_year=252)

    orders = portfolio.orders.records_readable
    assert tuple(orders["Size"]) == (2.0, 2.0)
    assert tuple(orders["Side"]) == ("Buy", "Sell")


def test_cash_sharing_executes_complete_nearest_quantities() -> None:
    first = InstrumentId.from_str("FIRST.XNAS")
    second = InstrumentId.from_str("SECOND.XNAS")
    index = pd.date_range("2026-01-01", periods=4)
    close = pd.DataFrame({first: 30.0, second: 30.0}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [("candidate", first), ("candidate", second)],
        names=["candidate", "symbol"],
    )
    allocations = pd.DataFrame(
        [[0.5, 0.5], [0.5, 0.5], [0.0, 0.0], [0.0, 0.0]],
        index=index,
        columns=columns,
    )
    config = PortfolioConfig(
        direction="longonly",
        init_cash=100.0,
        fees=0.0,
        slippage=0.0,
        fixed_fee=0.0,
        margin_interest_rate=0.0,
    )
    book = ResolvedBook(
        config,
        size_increment_by_instrument={first: 1.0, second: 1.0},
    )

    portfolio = simulate_portfolio_batch(close, allocations, book, periods_per_year=252)

    assert tuple(portfolio.orders.records_readable["Size"]) == (2.0, 2.0, 2.0, 2.0)
