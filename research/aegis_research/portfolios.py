from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig


def simulate_portfolio(
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    config: PortfolioConfig,
) -> vbt.Portfolio:
    common_index = close.index.intersection(entries.index).intersection(exits.index)
    aligned_close = close.loc[common_index]
    aligned_entries = entries.loc[common_index]
    aligned_exits = exits.loc[common_index]
    common_columns = aligned_close.columns.intersection(aligned_entries.columns).intersection(
        aligned_exits.columns
    )
    if common_columns.empty:
        raise ValueError("portfolio inputs must share at least one symbol column")
    aligned_close = aligned_close.loc[:, common_columns]
    aligned_entries = aligned_entries.loc[:, common_columns]
    aligned_exits = aligned_exits.loc[:, common_columns]
    return vbt.Portfolio.from_signals(
        close=aligned_close,
        entries=aligned_entries,
        exits=aligned_exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        size=config.size,
        size_type=config.size_type,
        direction=config.direction,
    )
