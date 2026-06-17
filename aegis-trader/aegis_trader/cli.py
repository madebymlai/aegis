"""Run entrypoint — assemble a run from ``book.toml`` + the environment.

This is the operator-facing seam (finding a5): given a ``--mode`` and a
``--book`` path it resolves the declarative book spec and (for paper/live) the
IBKR connection from the environment, then builds the real Nautilus config
objects — the strategy config with the mode-correct next-close TIF (ADR-0001),
plus the backtest engine config or the paper/live node config and IBKR client
dicts whose account ID comes from the environment, never a placeholder.

It assembles and validates the run configuration and logs a summary; feeding
market data and calling ``node.run()`` / ``engine.run()`` is the operator's
runtime step (the data source is mode- and deployment-specific).
"""

from __future__ import annotations

import argparse
import logging

from aegis_trader.backtest import (
    FxFetcher,
    OhlcvFetcher,
    book_return_stats,
    run_book_backtest,
    yfinance_fx,
    yfinance_ohlcv,
)
from aegis_trader.config import (
    IBConnectionSettings,
    find_book_config,
    load_book_config,
)
from aegis_trader.data.snapshot import SnapshotCache
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.trader.modes import (
    build_backtest_engine_config,
    build_live_data_client_config,
    build_live_exec_client_config,
    build_live_trading_node_config,
    build_paper_data_client_config,
    build_paper_exec_client_config,
    build_paper_trading_node_config,
    fill_time_in_force_for_mode,
)
from aegis_trader.trader.strategy import RebalanceStrategyConfig

_MODES = ("backtest", "paper", "live")

_log = logging.getLogger("aegis_trader")


def build_strategy_config(book: BookConfig, mode: str) -> RebalanceStrategyConfig:
    """Strategy config for *mode* — book carried, next-close TIF per ADR-0001."""
    return RebalanceStrategyConfig(
        book=book,
        fill_time_in_force=fill_time_in_force_for_mode(mode),
    )


def build_ib_client_configs(
    settings: IBConnectionSettings, mode: str,
) -> tuple[dict, dict]:
    """Map resolved connection settings onto the IBKR data/exec client dicts.

    The account ID flows from the environment (``settings``) into the exec
    client config — there is no placeholder in this path.
    """
    if mode == "paper":
        data = build_paper_data_client_config(
            ibg_host=settings.host, ibg_port=settings.port,
            ibg_client_id=settings.client_id,
        )
        execution = build_paper_exec_client_config(
            ibg_host=settings.host, ibg_port=settings.port,
            ibg_client_id=settings.client_id, account_id=settings.account_id,
        )
    elif mode == "live":
        data = build_live_data_client_config(
            ibg_host=settings.host, ibg_port=settings.port,
            ibg_client_id=settings.client_id,
        )
        execution = build_live_exec_client_config(
            ibg_host=settings.host, ibg_port=settings.port,
            ibg_client_id=settings.client_id, account_id=settings.account_id,
        )
    else:
        raise ValueError(f"mode {mode!r} has no IBKR connection (backtest is offline)")
    return data, execution


def _run_backtest(args: argparse.Namespace) -> int:
    """Run an offline backtest of the book end-to-end and summarize the outcome.

    Fully independent of ``--mode``: it resolves the book, runs the contract-driven
    runner with the default contract-aware fetchers, and reports the result.  With
    ``--data-cache DIR`` the fetchers are pinned to disk so identical runs are
    reproducible (the live providers are nondeterministic).
    """
    book_path = args.book if args.book is not None else find_book_config()
    fetch_ohlcv: OhlcvFetcher = yfinance_ohlcv
    fetch_fx: FxFetcher = yfinance_fx
    if args.data_cache is not None:
        cache = SnapshotCache(args.data_cache)
        fetch_ohlcv = cache.ohlcv(fetch_ohlcv)
        fetch_fx = cache.fx(fetch_fx)
    engine = run_book_backtest(
        book_path,
        start=args.start,
        end=args.end,
        fetch_ohlcv=fetch_ohlcv,
        fetch_fx=fetch_fx,
    )
    result = engine.get_result()
    fills = [order for order in engine.cache.orders() if order.is_closed]
    _log.info(
        "Backtest complete: %d fill(s) over %s..%s", len(fills), args.start, args.end
    )
    _log_performance(result, book_return_stats(engine))
    engine.dispose()
    return 0


def _log_performance(result, return_stats: dict[str, float]) -> None:
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


def main(argv: list[str] | None = None) -> int:
    """Run an offline ``backtest`` of the book, or assemble a ``--mode`` run config."""
    parser = argparse.ArgumentParser(
        prog="aegis-trader",
        description="Run the Aegis commingled book overlay.",
    )
    parser.add_argument(
        "--mode", choices=_MODES, help="assemble and validate a run config for this mode"
    )
    parser.add_argument(
        "--book",
        default=None,
        help="path to the book.toml spec "
        "(default: discover book.toml by walking up from the cwd)",
    )
    subparsers = parser.add_subparsers(dest="command")
    backtest_p = subparsers.add_parser(
        "backtest", help="run an offline backtest of the book end-to-end"
    )
    backtest_p.add_argument("--start", required=True, help="start date (YYYY-MM-DD)")
    backtest_p.add_argument("--end", required=True, help="end date (YYYY-MM-DD)")
    backtest_p.add_argument(
        "--book",
        default=None,
        help="path to the book.toml spec "
        "(default: discover book.toml by walking up from the cwd)",
    )
    backtest_p.add_argument(
        "--data-cache",
        default=None,
        metavar="DIR",
        help="pin provider data to this directory for reproducible runs "
        "(first run snapshots; later identical runs read the snapshot)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    if args.command == "backtest":
        return _run_backtest(args)

    if args.mode is None:
        parser.error(
            "a run mode is required: pass --mode {backtest,paper,live} "
            "or the 'backtest' subcommand"
        )

    book_path = args.book if args.book is not None else find_book_config()
    book = load_book_config(book_path)
    build_strategy_config(book, args.mode)
    _log.info(
        "Loaded book: %d sleeve(s), base_currency=%s, mode=%s",
        book.sleeve_count, book.base_currency, args.mode,
    )

    if args.mode == "backtest":
        engine_config = build_backtest_engine_config()
        _log.info(
            "Backtest engine configured (trader_id=%s). "
            "Add venues, instruments, and data, then run.",
            engine_config.trader_id,
        )
    else:
        settings = IBConnectionSettings.from_env(args.mode)
        node_config = (
            build_paper_trading_node_config(trader_id=settings.trader_id)
            if args.mode == "paper"
            else build_live_trading_node_config(trader_id=settings.trader_id)
        )
        build_ib_client_configs(settings, args.mode)
        _log.info(
            "%s node configured (env=%s) for account %s @ %s:%d. "
            "Register IBKR factories with the client configs and run.",
            args.mode, node_config.environment.value,
            settings.account_id, settings.host, settings.port,
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
