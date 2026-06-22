"""Trader backtest entrypoints.

The old trader-local Historical Store backtest runner was removed by the
market-data unification slice.  Research backtests now source native
InstrumentId bars through the catalog-backed data path; live/paper parity is
held at the Strategy/Cache boundary.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class TraderBacktestRemovedError(NotImplementedError):
    """Raised when callers use the removed Historical Store backtest runner."""


def run_book_backtest(
    book_path: str | Path,
    *,
    start: str,
    end: str,
    store_dir: Path | None = None,
    registry: object | None = None,
    venue: str = "SIM",
    starting_cash: float = 1_000_000.0,
    trader_id: str = "BACKTEST-001",
) -> Any:
    """Fail loudly instead of routing through the deleted Historical Store path."""
    _ = (book_path, start, end, store_dir, registry, venue, starting_cash, trader_id)
    raise TraderBacktestRemovedError(
        "the trader-local Historical Store backtest runner was removed; run "
        "research backtests through the catalog-backed RD path"
    )


def book_return_stats(_engine: object) -> dict[str, float]:
    """Return no stats for the removed trader-local backtest runner."""
    return {}
