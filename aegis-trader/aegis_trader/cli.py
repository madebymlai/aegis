"""Run entrypoint — the operator-facing commands.

Two surfaces, no ``--mode``:

- ``aegis-trader backtest --start --end [--book --catalog-path]`` runs an offline,
  catalog-only backtest of the book end-to-end.
- ``aegis-trader trader start [--book --pid-file]`` builds and runs the live
  ``TradingNode`` in the **foreground** (supervised by systemd/tmux); ``trader stop
  [--pid-file]`` signals a running one to shut down.  Paper vs live is decided
  *only* by the env connection's port (``IB_PORT``) — there is no mode.

The book spec is declarative (``book.toml``); the IBKR connection + account come
from the environment (``IB_*`` / ``TRADER_ID``), never the committed spec.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from aegis_trader.config import IBConnectionSettings, find_book_config

_log = logging.getLogger("aegis_trader")


def _run_backtest(args: argparse.Namespace) -> int:
    """Run an offline backtest of the book end-to-end and summarize the outcome."""
    from aegis_trader.backtest import book_return_stats, run_book_backtest

    book_path = args.book if args.book is not None else find_book_config()
    backtest = run_book_backtest(
        book_path,
        start=args.start,
        end=args.end,
        catalog_path=args.catalog_path,
    )
    engine = backtest.engine
    result = engine.get_result()
    fills = [order for order in engine.cache.orders() if order.is_closed]
    _log.info(
        "Backtest complete: %d fill(s) over %s..%s", len(fills), args.start, args.end
    )
    horizon = backtest.analytics_horizon
    _log.info(
        "Analytics horizon: %s (%d periods/yr), derived from the roster",
        horizon.bucket_timeframe,
        horizon.periods_per_year,
    )
    _log_performance(result, book_return_stats(engine, horizon), backtest.financing_totals)
    engine.dispose()
    return 0


def _log_performance(
    result,
    return_stats: dict[str, float],
    financing_totals: dict[str, float],
) -> None:
    """Report the performance summary — ``stats_pnls`` (per-currency PnL) plus the
    base-currency return stats (Sharpe, volatility, …) computed from the NAV curve.

    The book runs a multi-currency (``base_currency=None``) account, for which
    Nautilus' native ``stats_returns`` is unusable; ``return_stats`` is the
    base-currency series from :func:`book_return_stats` (aegis-rd-syp)."""
    _log.info("Orders: %d | Positions: %d", result.total_orders, result.total_positions)
    for currency, stats in (result.stats_pnls or {}).items():
        _log.info("PnL stats [%s]:", currency)
        for name, value in stats.items():
            _log.info("  %s: %s", name, value)
    if return_stats:
        _log.info("Return stats (base currency):")
        for name, value in return_stats.items():
            _log.info("  %s: %s", name, value)
    nonzero_financing = {
        currency: amount
        for currency, amount in financing_totals.items()
        if amount != 0.0
    }
    if nonzero_financing:
        _log.info("Financing costs (totals, by currency):")
        for currency, amount in sorted(nonzero_financing.items()):
            _log.info("  %s: %s", currency, amount)


def _trader_start(args: argparse.Namespace) -> int:
    """Build and run the live trader in the foreground (paper vs live = ``IB_PORT``)."""
    from aegis_trader.trader.node import start_trader

    book_path = args.book if args.book is not None else find_book_config()
    connection = IBConnectionSettings.from_env()
    _log.info(
        "Starting live trader for account %s on IB_PORT=%d (port decides paper vs live)",
        connection.account_id, connection.port,
    )
    return start_trader(book_path, connection, pid_file=args.pid_file)


def _trader_stop(args: argparse.Namespace) -> int:
    """Signal a running live trader to shut down gracefully (SIGTERM to its pidfile)."""
    from aegis_trader.trader.node import stop_trader

    return stop_trader(pid_file=args.pid_file)


def _add_book_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--book",
        default=None,
        help="path to the book.toml spec "
        "(default: discover book.toml by walking up from the cwd)",
    )


def _add_pid_file_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pid-file",
        default=None,
        metavar="FILE",
        type=Path,
        help="pidfile path (default: aegis-trader.pid in the per-user runtime dir)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aegis-trader",
        description="Run the Aegis commingled book overlay.",
    )
    subparsers = parser.add_subparsers(dest="command")

    backtest_p = subparsers.add_parser(
        "backtest", help="run an offline backtest of the book end-to-end"
    )
    backtest_p.add_argument("--start", required=True, help="start date (YYYY-MM-DD)")
    backtest_p.add_argument("--end", required=True, help="end date (YYYY-MM-DD)")
    _add_book_arg(backtest_p)
    backtest_p.add_argument(
        "--catalog-path",
        default=None,
        metavar="DIR",
        type=Path,
        help="read the Nautilus ParquetDataCatalog from DIR (default: aegis-data OS catalog)",
    )

    trader_p = subparsers.add_parser(
        "trader", help="run the live trading daemon (paper vs live = IB_PORT)"
    )
    trader_sub = trader_p.add_subparsers(dest="trader_command")
    start_p = trader_sub.add_parser(
        "start", help="build and run the live TradingNode in the foreground"
    )
    _add_book_arg(start_p)
    _add_pid_file_arg(start_p)
    stop_p = trader_sub.add_parser(
        "stop", help="signal a running live trader to stop (SIGTERM)"
    )
    _add_pid_file_arg(stop_p)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run an offline ``backtest`` of the book, or ``trader start``/``stop`` the
    live daemon."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    if args.command == "backtest":
        return _run_backtest(args)
    if args.command == "trader":
        if args.trader_command == "start":
            return _trader_start(args)
        if args.trader_command == "stop":
            return _trader_stop(args)
        parser.error("trader requires a subcommand: 'start' or 'stop'")

    parser.error("a command is required: 'backtest' or 'trader start|stop'")
    return 2  # unreachable: parser.error raises SystemExit


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
