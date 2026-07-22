from __future__ import annotations

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.portfolio_simulation._simulation import (
    simulate_portfolio_batch,
)


def test_portfolio_orders_follow_each_instruments_catalog_size_increment() -> None:
    whole = InstrumentId.from_str("WHOLE.XNAS")
    second = InstrumentId.from_str("SECOND.XNAS")
    index = pd.date_range("2026-01-01", periods=4)
    close = pd.DataFrame({whole: 30.0, second: 30.0}, index=index)
    columns = pd.MultiIndex.from_tuples(
        [("candidate", whole), ("candidate", second)],
        names=["candidate", "symbol"],
    )
    allocations = pd.DataFrame(
        [[0.5, 0.5], [0.5, 0.5], [0.0, 0.0], [0.0, 0.0]],
        index=index,
        columns=columns,
    )
    config = PortfolioConfig(
        gross_cap=1.0,
        direction="longonly",
        init_cash=100.0,
        fees=0.0,
        slippage=0.0,
        fixed_fee=0.0,
        margin_interest_rate=0.0,
    )
    book = ResolvedBook(
        config,
        size_increment_by_instrument={whole: 1.0, second: 1.0},
    )

    portfolio = simulate_portfolio_batch(close, allocations, book, periods_per_year=252)

    np.testing.assert_allclose(portfolio.assets.iloc[1].to_numpy(), [1.0, 1.0])
    np.testing.assert_allclose(portfolio.assets.iloc[-1].to_numpy(), [0.0, 0.0])
    whole_orders = portfolio.orders.records_readable.query("Column == @whole")["Size"]
    assert all(float(size).is_integer() for size in whole_orders)
