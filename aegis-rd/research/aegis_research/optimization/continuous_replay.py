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
    PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
    VBT_LEVERAGE_MODE,
    VBT_NEXT_CLOSE_PRICE,
    VBT_NEXT_OPEN_PRICE,
    VBT_PF_METHOD,
    VBT_RESOLVED_SIZE_TYPE,
    portfolio_replay_implementation_fingerprint,
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


def continuous_replay_protocol(
    *,
    fill_timing: str,
    direction: str,
    scored_start: int,
    sim_end: int,
) -> dict[str, object]:
    """Publish the pinned causal VBT replay protocol from its implementation owner."""
    if fill_timing not in ("next_open", "next_close"):
        raise ValueError("continuous replay evidence requires next_open or next_close")
    price = VBT_NEXT_OPEN_PRICE if fill_timing == "next_open" else VBT_NEXT_CLOSE_PRICE
    return {
        "schema_version": PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION,
        "implementation_fingerprint": portfolio_replay_implementation_fingerprint(),
        "portfolio_optimizer": {
            "valid_only": True,
            "nonzero_only": False,
            "unique_only": False,
        },
        "portfolio": {
            "pf_method": VBT_PF_METHOD,
            "size_type": VBT_RESOLVED_SIZE_TYPE,
            "direction": direction,
            "cash_sharing": True,
            "call_seq": "auto",
            "group_by": "ExceptLevel(Symbol)",
            "sim_start": scored_start,
            "sim_start_inclusive": True,
            "sim_end": sim_end,
            "sim_end_exclusive": True,
            "leverage_mode": VBT_LEVERAGE_MODE,
            "log": True,
            "save_returns": False,
        },
        "fill_timing": {
            "aegis": fill_timing,
            "vbt_price": price,
            "input_from_ago": None,
            "vbt_effective_delay_bars": 1,
        },
        "preserved_contracts": {
            "callback_staticization": "drift_band_callback_staticization.v1",
            "costs_leverage_dividends": "resolved_book_portfolio_terms.v1",
            "no_cash_rejection": "fail_closed.v1",
        },
    }


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


__all__ = ["ContinuousReplayResult", "continuous_replay_protocol", "replay_candidates"]
