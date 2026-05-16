from __future__ import annotations

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig


def simulate_portfolio(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    config: PortfolioConfig,
) -> vbt.Portfolio:
    common_index = close.index.intersection(entries.index).intersection(exits.index)
    aligned_close = close.loc[common_index]
    aligned_entries = entries.loc[common_index]
    aligned_exits = exits.loc[common_index]
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
