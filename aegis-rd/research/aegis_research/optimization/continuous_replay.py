"""One uninterrupted VBT replay for fixed Candidate allocations.

The public operation in this module owns the execution boundary: callers hand it
materialized Candidate allocations and one common derived ``scored_start``. It
returns the unchanged full Portfolio together with canonical continuous-path
views. Observation Blocks are deliberately outside this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
from aegis_data.distributions import Distribution
from aegis_runtime.currency import CurrencyConversion
from vectorbtpro import vbt

from research.aegis_research.optimization.window_evaluation._simulation import (
    simulate_portfolio_batch,
)
from research.aegis_research.optimization.window_evaluation.resolved_book import (
    ResolvedBook,
)


@dataclass(frozen=True)
class ContinuousReplayResult:
    """The canonical full-path result of one Candidate-batched replay."""

    portfolio: vbt.Portfolio
    scored_start: int
    sim_end: int

    @property
    def values(self) -> pd.Series | pd.DataFrame:
        return self.portfolio.value

    @property
    def returns(self) -> pd.Series | pd.DataFrame:
        return self.portfolio.returns

    @property
    def positions(self) -> pd.DataFrame:
        return self.portfolio.assets

    @property
    def cash(self) -> pd.Series | pd.DataFrame:
        return self.portfolio.cash

    @property
    def orders(self) -> pd.DataFrame:
        return self.portfolio.orders.records_readable

    @property
    def costs(self) -> pd.Series:
        orders = self.orders
        return orders["Fees"].copy()

    @property
    def trades(self) -> pd.DataFrame:
        return self.portfolio.trades.records_readable


def replay_candidates(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    book: ResolvedBook,
    *,
    scored_start: int,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    periods_per_year: int,
    distributions: Sequence[Distribution] = (),
    currency_conversion: CurrencyConversion | None = None,
) -> ContinuousReplayResult:
    """Replay fixed Candidate columns once over the complete Development path."""
    if not isinstance(scored_start, int) or isinstance(scored_start, bool):
        raise TypeError("continuous replay scored_start must be an integer row position")
    if scored_start < 0 or scored_start >= len(close.index):
        raise ValueError("continuous replay scored_start must select a row in Close")
    if book.config.fill_timing == "same_close":
        raise ValueError(
            "continuous replay rejects same_close for Close-dependent allocations"
        )

    portfolio = simulate_portfolio_batch(
        close,
        allocations,
        book,
        scored_start=scored_start,
        open_=open_,
        market_index=market_index,
        periods_per_year=periods_per_year,
        distributions=distributions,
        currency_conversion=currency_conversion,
    )
    return ContinuousReplayResult(
        portfolio=portfolio,
        scored_start=scored_start,
        sim_end=len(close.index),
    )


__all__ = ["ContinuousReplayResult", "replay_candidates"]
