"""Integration tests for the run entrypoint (Wave D / aegis-rd-bwb.4).

The CLI is the seam that closes the 'no run configuration' gap (finding a5): a
``book.toml`` + the environment assemble into the real Nautilus config objects —
the strategy config (with the mode-correct next-close TIF), the backtest engine
config, or the paper/live node config plus IBKR client dicts whose account comes
from the environment.  Backtests run from the Historical Store; paper/live still
leave venue data and ``node.run()`` to the operator.
"""

from __future__ import annotations

import logging
import types

import pytest
from nautilus_trader.model.enums import TimeInForce

from aegis_trader.cli import build_ib_client_configs, build_strategy_config, main
from aegis_trader.config import ConnectionConfigError, IBConnectionSettings
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName

_BOOK_TOML = """
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "trend.whl"
risk_share = 1.0
group = "Floor"
"""


def _book() -> BookConfig:
    return BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"),
                              wheel_filename="trend.whl", risk_share=1.0),),
        base_currency="EUR",
    )


def _write_book(tmp_path):
    path = tmp_path / "book.toml"
    path.write_text(_BOOK_TOML)
    return path


class _FakeEngine:
    """Minimal stand-in for the BacktestEngine the patched runner returns."""

    class _Cache:
        def orders(self):
            return []

    class _Trader:
        def actors(self):
            return []  # no BookEquityRecorder -> book_return_stats yields {}

    def __init__(self) -> None:
        self.cache = _FakeEngine._Cache()
        self.trader = _FakeEngine._Trader()
        self.disposed = False

    def get_result(self):
        return types.SimpleNamespace(
            total_orders=0,
            total_positions=0,
            stats_pnls={"EUR": {"PnL (total)": 12345.0}},
            # Native multi-currency stats_returns is unusable (sentinel must NOT
            # surface — the CLI reports book_return_stats instead; aegis-rd-syp).
            stats_returns={"Sharpe Ratio (252 days)": 99.99},
        )

    def dispose(self) -> None:
        self.disposed = True


def test_strategy_config_for_backtest_uses_plain_market():
    """Backtest -> fill_time_in_force None (plain MARKET at the close)."""
    cfg = build_strategy_config(_book(), "backtest")
    assert cfg.book.base_currency == "EUR"
    assert cfg.fill_time_in_force is None


def test_strategy_config_for_paper_uses_market_on_close():
    """Paper/live -> AT_THE_CLOSE (Market-on-Close into the auction)."""
    cfg = build_strategy_config(_book(), "paper")
    assert cfg.fill_time_in_force == TimeInForce.AT_THE_CLOSE


def test_ib_client_configs_wire_account_from_settings():
    """The env-driven account flows into the exec config; host/port wired."""
    settings = IBConnectionSettings(
        host="10.0.0.5", port=4002, client_id=9,
        account_id="DU1234567", trader_id="BOOK-EU-01",
    )

    data, execution = build_ib_client_configs(settings, "paper")

    assert execution["account_id"] == "DU1234567"
    assert execution["ibg_host"] == "10.0.0.5"
    assert execution["ibg_port"] == 4002
    assert data["ibg_client_id"] == 9


def test_main_backtest_assembles_run_from_book(tmp_path):
    """Backtest mode loads the book.toml and assembles a run (closes a5)."""
    book_path = _write_book(tmp_path)
    assert main(["--mode", "backtest", "--book", str(book_path)]) == 0


def test_backtest_subcommand_runs_the_runner(tmp_path, monkeypatch):
    """`aegis-trader backtest --start --end` runs run_book_backtest with the book
    and window, using Store Read inputs."""
    book_path = _write_book(tmp_path)
    calls: dict = {}

    def fake_runner(path, *, start, end, store_dir=None, **kwargs):
        calls.update(path=path, start=start, end=end, store_dir=store_dir)
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.cli.run_book_backtest", fake_runner)

    rc = main(
        ["backtest", "--start", "2020-01-01", "--end", "2020-06-01",
         "--book", str(book_path)]
    )

    assert rc == 0
    assert calls["path"] == str(book_path)
    assert calls["start"] == "2020-01-01"
    assert calls["end"] == "2020-06-01"
    assert calls["store_dir"] is None


def test_backtest_subcommand_passes_store_dir_override(tmp_path, monkeypatch):
    """`--store-dir DIR` passes the Historical Store override to the runner."""
    book_path = _write_book(tmp_path)
    store_dir = tmp_path / "store"
    captured: dict = {}

    def fake_runner(path, *, start, end, store_dir=None, **kwargs):
        captured["store_dir"] = store_dir
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.cli.run_book_backtest", fake_runner)

    rc = main(
        ["backtest", "--start", "2020-01-01", "--end", "2020-06-01",
         "--book", str(book_path), "--store-dir", str(store_dir)]
    )

    assert rc == 0
    assert captured["store_dir"] == store_dir


def test_backtest_subcommand_discovers_book_when_omitted(tmp_path, monkeypatch):
    """With --book omitted, the backtest subcommand discovers book.toml from cwd."""
    _write_book(tmp_path)
    work = tmp_path / "deploy"
    work.mkdir()
    monkeypatch.chdir(work)
    seen: dict = {}

    def fake_runner(path, *, start, end, store_dir=None, **kwargs):
        seen["path"] = path
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.cli.run_book_backtest", fake_runner)

    rc = main(["backtest", "--start", "2020-01-01", "--end", "2020-06-01"])

    assert rc == 0
    assert str(seen["path"]) == str(tmp_path / "book.toml")


def test_backtest_subcommand_reports_performance_stats(tmp_path, monkeypatch, caplog):
    """The backtest subcommand surfaces per-currency PnL (stats_pnls) plus the
    base-currency return stats from book_return_stats — not Nautilus' native
    multi-currency stats_returns, which is unusable for a base_currency=None
    account (aegis-rd-syp)."""
    book_path = _write_book(tmp_path)
    monkeypatch.setattr(
        "aegis_trader.cli.run_book_backtest", lambda path, **kw: _FakeEngine()
    )
    monkeypatch.setattr(
        "aegis_trader.cli.book_return_stats",
        lambda engine: {"Sharpe Ratio (252 days)": 0.87},
    )

    with caplog.at_level(logging.INFO, logger="aegis_trader"):
        rc = main(
            ["backtest", "--start", "2019-01-01", "--end", "2020-01-01",
             "--book", str(book_path)]
        )

    assert rc == 0
    assert "PnL (total)" in caplog.text  # stats_pnls surfaced
    assert "12345" in caplog.text
    assert "Sharpe Ratio (252 days)" in caplog.text  # return stats surfaced
    assert "0.87" in caplog.text  # the base-currency Sharpe (book_return_stats)
    assert "99.99" not in caplog.text  # native stats_returns is NOT used


def test_main_discovers_book_from_cwd_when_omitted(tmp_path, monkeypatch):
    """Omitting --book discovers book.toml by walking up from the cwd."""
    _write_book(tmp_path)
    work = tmp_path / "deploy"
    work.mkdir()
    monkeypatch.chdir(work)
    assert main(["--mode", "backtest"]) == 0


def test_main_paper_resolves_account_from_env(tmp_path, monkeypatch):
    book_path = _write_book(tmp_path)
    monkeypatch.setenv("IB_ACCOUNT_ID", "DU1234567")
    assert main(["--mode", "paper", "--book", str(book_path)]) == 0


def test_main_fails_closed_without_mode_or_subcommand(tmp_path, monkeypatch):
    """Invoked with neither --mode nor the backtest subcommand, the CLI fails
    closed (parser error) rather than silently no-opping."""
    monkeypatch.chdir(tmp_path)  # no book.toml here, so any no-op would surface
    with pytest.raises(SystemExit):
        main([])


def test_main_paper_fails_closed_without_account(tmp_path, monkeypatch):
    """No account in the env -> the paper run refuses to assemble."""
    book_path = _write_book(tmp_path)
    monkeypatch.delenv("IB_ACCOUNT_ID", raising=False)
    with pytest.raises(ConnectionConfigError, match="IB_ACCOUNT_ID"):
        main(["--mode", "paper", "--book", str(book_path)])
