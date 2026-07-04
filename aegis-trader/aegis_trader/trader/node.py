"""The live trading node — broker-neutral Nautilus ``TradingNode`` + the
``trader start``/``stop`` lifecycle (ADR-0003 amendment, aegis-rd-r8b.8).

This module owns the *live* node: its ``Environment.LIVE`` config (live RiskEngine,
cache, logging, shared catalog) and the foreground run/stop daemon.  It is
**broker-neutral** — no ``ibg_*``/``IDEALPRO`` vocabulary and no IBKR SDK import.
The one broker touch is a single call, :func:`aegis_data.ibkr.attach_live_clients`,
which wires Nautilus's stock IBKR clients onto the node; everything IBKR lives
behind that seam (and its lazy ``ibapi`` boundary), so importing this module never
needs ``ibapi``.

Lifecycle (the CLI now owns ``node.run()``):

- ``trader start`` → :func:`start_trader`: build the live node, register the IBKR
  factories, add the ``RebalanceStrategy``, write a pidfile, and run in the
  **foreground** (supervised by systemd/tmux) with the Nautilus-correct shutdown.
- ``trader stop`` → :func:`stop_trader`: read the pidfile and send ``SIGTERM``.

Paper vs live is **only** the connection's port (IBKR's own guidance) — there is
no mode.  Next-close execution carries ``AT_THE_CLOSE`` live (ADR-0001).
"""

from __future__ import annotations

import logging
import os
import signal
import tempfile
from pathlib import Path

import msgspec
from nautilus_trader.common import Environment
from nautilus_trader.config import (
    CacheConfig,
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.persistence.config import DataCatalogConfig

from aegis_data.catalog import catalog_root
from aegis_data.ibkr import attach_live_clients

from aegis_trader.bundles.book_sleeves import (
    SleeveBundles,
    load_book_sleeves,
    union_loadable_instrument_ids,
)
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import IBConnectionSettings, load_book_config
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.risk_guard import RiskGuardConfig
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_log = logging.getLogger("aegis_trader")

# Next-close execution TIF live (ADR-0001): a Market-on-Close order into the
# closing auction.  The backtest counterpart is a plain MARKET (``None``), set by
# the backtest runner — the two model the same fill point (the close).
LIVE_FILL_TIME_IN_FORCE: TimeInForce = TimeInForce.AT_THE_CLOSE

_PID_FILE_NAME = "aegis-trader.pid"


class TraderNotRunningError(RuntimeError):
    """No live trader is running (the pidfile ``trader stop`` expects is absent)."""


# ── live node config (broker-neutral) ─────────────────────────────────────────


def build_live_risk_engine_config(
    risk_guard_config: RiskGuardConfig | None = None,
) -> LiveRiskEngineConfig:
    """The live RiskEngine config (``TradingNode`` requires the live variant).

    An always-on, defense-in-depth guard over the sizing layer — never bypassed —
    carrying the RiskGuard's order submit/modify rate limits.  Per-instrument
    max-notional caps depend on live NAV and are applied by the strategy at
    startup (``RebalanceStrategy.risk_engine_config_dict``).
    """
    guard = risk_guard_config or RiskGuardConfig()
    return LiveRiskEngineConfig(
        bypass=False,
        max_order_submit_rate=guard.max_order_submit_rate,
        max_order_modify_rate=guard.max_order_modify_rate,
    )


def build_live_node_config(*, trader_id: str | None = None) -> TradingNodeConfig:
    """Build the live ``TradingNodeConfig`` (broker-neutral).

    Runs under ``Environment.LIVE`` with reconciliation, the live RiskEngine, a
    cache, logging, and the shared aegis-data catalog wired in (ADR-0006): a
    startup ``request_bars(update_catalog=True)`` then serves history from the
    catalog and tops up only the missing IBKR tail, so research and live warm from
    the *same* corpus with no cold-start lookback gap.  The broker's data/exec
    clients are wired separately by :func:`aegis_data.ibkr.attach_live_clients`.

    *trader_id* is the Broker Connection's (``connection.trader_id``); when omitted
    Nautilus's own ``TradingNodeConfig`` default applies — the default lives in one
    place, not mirrored here.

    The data engine turns off ``time_bars_build_with_no_updates`` (r8b.2 AC6, still
    governing under r8b.9 Model 2): the continuous series is materialised off-cache by the
    feed, so the only thing subscribed on this node is each root's **raw front leg**
    (execution routing + the feed's daily wake).  That daily subscription inherits the
    ``DataEngineConfig`` default ``True``, which emits non-trading-day flat bars → spurious
    ``on_bar`` wakes and stale marks; off here keeps the raw-leg cadence to real closes only
    (prototype NOTES.md V5 CONFIG finding).
    """
    config = TradingNodeConfig(
        environment=Environment.LIVE,
        data_engine=LiveDataEngineConfig(time_bars_build_with_no_updates=False),
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        risk_engine=build_live_risk_engine_config(),
        cache=CacheConfig(),
        logging=LoggingConfig(),
        catalogs=[DataCatalogConfig(path=str(catalog_root()))],
    )
    if trader_id is None:
        return config
    return msgspec.structs.replace(config, trader_id=trader_id)


# ── live node assembly ────────────────────────────────────────────────────────


def build_live_node(
    book: BookConfig,
    connection: IBConnectionSettings,
    *,
    registry: BundleRegistryPort | None = None,
) -> TradingNode:
    """Assemble a built, runnable live ``TradingNode`` for *book* over *connection*.

    Loads the book's sleeves, derives the InstrumentProvider ``load_ids`` from the
    union of their declared native ids, wires IBKR's stock clients/factories via
    the single broker seam, builds the node, and adds the strategy.  Paper vs live
    is decided entirely by ``connection`` (its port).
    """
    registry = registry if registry is not None else EntryPointBundleRegistry()
    sleeves = load_book_sleeves(book, registry)
    instrument_ids = union_loadable_instrument_ids(sleeves)

    node = TradingNode(config=build_live_node_config(trader_id=connection.trader_id))
    attach_live_clients(node, connection, instrument_ids)
    node.build()
    node.trader.add_strategy(build_live_strategy(book, sleeves))
    return node


def build_live_strategy(book: BookConfig, sleeves: SleeveBundles) -> RebalanceStrategy:
    """The live ``RebalanceStrategy`` for *book*: next-close ``AT_THE_CLOSE`` and
    cache warmup on start, with each sleeve's bundle registered."""
    strategy = RebalanceStrategy(
        RebalanceStrategyConfig(
            book=book,
            fill_time_in_force=LIVE_FILL_TIME_IN_FORCE,
            warmup_cache_on_start=True,
        )
    )
    for name, bundle in sleeves:
        strategy.register_sleeve(name, bundle)
    return strategy


# ── run / stop lifecycle ──────────────────────────────────────────────────────


def start_trader(
    book_path: str | Path,
    connection: IBConnectionSettings,
    *,
    pid_file: Path | None = None,
    registry: BundleRegistryPort | None = None,
) -> int:
    """Build and run the live trader for the book at *book_path* in the foreground."""
    book = load_book_config(book_path)
    node = build_live_node(book, connection, registry=registry)
    return run_node(node, pid_file=pid_file or default_pid_file())


def run_node(node: TradingNode, *, pid_file: Path) -> int:
    """Run *node* in the foreground until stopped, then dispose — the Nautilus
    canonical shutdown.

    Nautilus's kernel installs the SIGTERM/SIGINT loop handlers itself (they call
    ``node.stop()``), so on a delivered signal ``node.run()`` returns and the
    ``finally`` tears the node down; the ``except KeyboardInterrupt`` is the
    canonical safety net for a Ctrl-C before the loop is running.  ``trader stop``
    delivers SIGTERM to the pidfile this writes.
    """
    _write_pid_file(pid_file)
    try:
        node.run()
    except KeyboardInterrupt:
        _log.info("Interrupt received; stopping the trader")
    finally:
        try:
            node.stop()
        finally:
            node.dispose()
        _remove_pid_file(pid_file)
    return 0


def stop_trader(*, pid_file: Path | None = None) -> int:
    """Stop a running live trader: read its pidfile and send ``SIGTERM``."""
    target = pid_file or default_pid_file()
    pid = _read_pid_file(target)
    os.kill(pid, signal.SIGTERM)
    _log.info("Sent SIGTERM to trader pid %d (%s)", pid, target)
    return 0


def default_pid_file() -> Path:
    """The default pidfile in the per-user runtime dir (``--pid-file`` overrides)."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime_dir) if runtime_dir else Path(tempfile.gettempdir())
    return base / _PID_FILE_NAME


def _write_pid_file(pid_file: Path) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))


def _remove_pid_file(pid_file: Path) -> None:
    pid_file.unlink(missing_ok=True)


def _read_pid_file(pid_file: Path) -> int:
    try:
        raw = pid_file.read_text()
    except FileNotFoundError as exc:
        raise TraderNotRunningError(
            f"no trader pidfile at {pid_file}; is the trader running?"
        ) from exc
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise TraderNotRunningError(
            f"trader pidfile {pid_file} is malformed: {raw!r}"
        ) from exc
