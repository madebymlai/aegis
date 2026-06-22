from __future__ import annotations

import pytest

from aegis_trader.backtest import TraderBacktestRemovedError, run_book_backtest


def test_removed_trader_backtest_runner_fails_loudly(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(
        """
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "trend.whl"
risk_share = 1.0
""".strip()
    )

    with pytest.raises(TraderBacktestRemovedError, match="catalog-backed RD path"):
        run_book_backtest(book_path, start="2024-01-01", end="2024-02-01")
