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

from aegis_trader.config import (
    IBConnectionSettings,
    find_book_config,
    load_book_config,
)
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


def main(argv: list[str] | None = None) -> int:
    """Assemble and validate the run configuration for the requested mode."""
    parser = argparse.ArgumentParser(
        prog="aegis-trader",
        description="Run the Aegis commingled book overlay in a given mode.",
    )
    parser.add_argument("--mode", required=True, choices=_MODES)
    parser.add_argument(
        "--book",
        default=None,
        help="path to the book.toml spec "
        "(default: discover book.toml by walking up from the cwd)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

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
