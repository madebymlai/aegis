"""Integration tests for the run entrypoint.

The CLI has two surfaces, no ``--mode``: ``aegis-trader backtest --start --end``
runs an offline catalog-backed backtest of the book; ``aegis-trader trader
start``/``stop`` runs and signals the live daemon.  ``trader start`` resolves the
Broker Connection from the environment (paper vs live is only ``IB_PORT``) and
fails closed when the required env is absent.
"""

from __future__ import annotations

import logging
import types

import pytest

from aegis_trader.cli import main
from aegis_trader.config import ConnectionConfigError

_BOOK_TOML = """
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "trend.whl"
risk_share = 1.0
group = "Floor"
"""


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


# --------------------------------------------------------------------------- #
# backtest subcommand (offline, catalog-only) — unchanged behaviour
# --------------------------------------------------------------------------- #


def test_backtest_subcommand_runs_the_runner(tmp_path, monkeypatch):
    """`aegis-trader backtest --start --end` runs run_book_backtest with the book
    and window, using catalog inputs."""
    book_path = _write_book(tmp_path)
    calls: dict = {}

    def fake_runner(path, *, start, end, catalog_path=None, **kwargs):
        calls.update(path=path, start=start, end=end, catalog_path=catalog_path)
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.backtest.run_book_backtest", fake_runner)

    rc = main(
        ["backtest", "--start", "2020-01-01", "--end", "2020-06-01",
         "--book", str(book_path)]
    )

    assert rc == 0
    assert calls["path"] == str(book_path)
    assert calls["start"] == "2020-01-01"
    assert calls["end"] == "2020-06-01"
    assert calls["catalog_path"] is None


def test_backtest_subcommand_passes_catalog_path_override(tmp_path, monkeypatch):
    """`--catalog-path DIR` passes the catalog override to the runner."""
    book_path = _write_book(tmp_path)
    catalog_path = tmp_path / "catalog"
    captured: dict = {}

    def fake_runner(path, *, start, end, catalog_path=None, **kwargs):
        captured["catalog_path"] = catalog_path
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.backtest.run_book_backtest", fake_runner)

    rc = main(
        ["backtest", "--start", "2020-01-01", "--end", "2020-06-01",
         "--book", str(book_path), "--catalog-path", str(catalog_path)]
    )

    assert rc == 0
    assert captured["catalog_path"] == catalog_path


def test_backtest_subcommand_discovers_book_when_omitted(tmp_path, monkeypatch):
    """With --book omitted, the backtest subcommand discovers book.toml from cwd."""
    _write_book(tmp_path)
    work = tmp_path / "deploy"
    work.mkdir()
    monkeypatch.chdir(work)
    seen: dict = {}

    def fake_runner(path, *, start, end, catalog_path=None, **kwargs):
        seen["path"] = path
        return _FakeEngine()

    monkeypatch.setattr("aegis_trader.backtest.run_book_backtest", fake_runner)

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
        "aegis_trader.backtest.run_book_backtest", lambda path, **kw: _FakeEngine()
    )
    monkeypatch.setattr(
        "aegis_trader.backtest.book_return_stats",
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


# --------------------------------------------------------------------------- #
# trader start / stop (live daemon)
# --------------------------------------------------------------------------- #


def test_trader_start_resolves_connection_from_env_and_runs(tmp_path, monkeypatch):
    """`trader start` resolves the env Broker Connection (port = paper/live) and
    hands the book path + connection + pidfile to the node lifecycle."""
    book_path = _write_book(tmp_path)
    pid_file = tmp_path / "trader.pid"
    monkeypatch.setenv("IB_ACCOUNT_ID", "DU1234567")
    monkeypatch.setenv("IB_PORT", "4002")
    captured: dict = {}

    def fake_start(path, connection, *, pid_file=None, registry=None):
        captured.update(path=path, connection=connection, pid_file=pid_file)
        return 0

    monkeypatch.setattr("aegis_trader.trader.node.start_trader", fake_start)

    rc = main(["trader", "start", "--book", str(book_path), "--pid-file", str(pid_file)])

    assert rc == 0
    assert captured["path"] == str(book_path)
    assert captured["connection"].account_id == "DU1234567"
    assert captured["connection"].port == 4002
    assert captured["pid_file"] == pid_file


def test_trader_start_fails_closed_without_account(tmp_path, monkeypatch):
    """No account in the env -> the live run refuses to start."""
    book_path = _write_book(tmp_path)
    monkeypatch.delenv("IB_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("IB_PORT", "4002")
    with pytest.raises(ConnectionConfigError, match="IB_ACCOUNT_ID"):
        main(["trader", "start", "--book", str(book_path)])


def test_trader_start_fails_closed_without_port(tmp_path, monkeypatch):
    """No IB_PORT in the env -> refuse to start (the port is the paper/live switch)."""
    book_path = _write_book(tmp_path)
    monkeypatch.setenv("IB_ACCOUNT_ID", "DU1234567")
    monkeypatch.delenv("IB_PORT", raising=False)
    with pytest.raises(ConnectionConfigError, match="IB_PORT"):
        main(["trader", "start", "--book", str(book_path)])


def test_trader_stop_signals_via_the_node_lifecycle(tmp_path, monkeypatch):
    pid_file = tmp_path / "trader.pid"
    captured: dict = {}

    def fake_stop(*, pid_file=None):
        captured["pid_file"] = pid_file
        return 0

    monkeypatch.setattr("aegis_trader.trader.node.stop_trader", fake_stop)

    rc = main(["trader", "stop", "--pid-file", str(pid_file)])

    assert rc == 0
    assert captured["pid_file"] == pid_file


def test_trader_without_subcommand_fails_closed():
    with pytest.raises(SystemExit):
        main(["trader"])


def test_main_fails_closed_without_a_command(tmp_path, monkeypatch):
    """Invoked with no command, the CLI fails closed (parser error) rather than
    silently no-opping."""
    monkeypatch.chdir(tmp_path)  # no book.toml here, so any no-op would surface
    with pytest.raises(SystemExit):
        main([])
