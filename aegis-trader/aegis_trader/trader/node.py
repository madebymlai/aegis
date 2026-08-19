"""The live trading node — broker-neutral Nautilus ``TradingNode`` + the
``trader start``/``stop`` lifecycle (ADR-0003 amendment, aegis-rd-r8b.8).

This module owns the *live* node: its ``Environment.LIVE`` config (cache, logging,
shared catalog) and the foreground run/stop daemon.  It is
**broker-neutral** — no ``ibg_*``/``IDEALPRO`` vocabulary and no IBKR SDK import.
The one broker touch is a single call, :func:`aegis_data.ibkr.live_clients`,
which supplies Nautilus's stock IBKR client configs and factories; everything IBKR lives
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

import fcntl
import logging
import os
import signal
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

import msgspec
from nautilus_trader.common import Environment
from nautilus_trader.common.messages import ShutdownSystem
from nautilus_trader.config import (
    CacheConfig,
    LiveDataClientConfig,
    LiveDataEngineConfig,
    LiveExecClientConfig,
    LiveExecEngineConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.persistence.config import DataCatalogConfig
from nautilus_trader.portfolio.config import PortfolioConfig

from aegis_data.catalog import catalog_root, open_catalog
from aegis_data.custom_data import CustomDataAdapterMap
from aegis_data.custom_kinds import CustomDataRegistry
from aegis_data.ibkr import live_clients
from aegis_data.storage import Catalog

from aegis_trader.bundles.book import AssembledBook, assemble_book
from aegis_trader.bundles.marking import recorded_marking_resolver
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import IBConnectionSettings, load_book_config
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.trader.live_custom_data import (
    build_live_sleeve_arrays,
    live_custom_data,
    warm_live_custom_data,
)
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig
from aegis_trader.trader.startup_fast_forward import RECOVERY_TOPIC, RecoveryUpdate

_log = logging.getLogger("aegis_trader")

# Next-close execution TIF live (ADR-0001): a Market-on-Close order into the
# closing auction.  The backtest counterpart is a plain MARKET (``None``), set by
# the backtest runner — the two model the same fill point (the close).
LIVE_FILL_TIME_IN_FORCE: TimeInForce = TimeInForce.AT_THE_CLOSE

_PID_FILE_NAME = "aegis-trader.pid"


class TraderNotRunningError(RuntimeError):
    """No live trader is running: the pidfile is absent, or no process holds it."""


class TraderAlreadyRunningError(RuntimeError):
    """A live trader already holds the pidfile this one was asked to take."""


# ── live node config (broker-neutral) ─────────────────────────────────────────


def build_live_node_config(
    *,
    trader_id: str | None = None,
    use_mark_prices: bool = False,
    data_clients: Mapping[str, LiveDataClientConfig] | None = None,
    exec_clients: Mapping[str, LiveExecClientConfig] | None = None,
) -> TradingNodeConfig:
    """Build the live ``TradingNodeConfig`` (broker-neutral).

    Runs under ``Environment.LIVE`` with reconciliation, a cache, logging, and the
    shared aegis-data catalog wired in (ADR-0006): a startup
    ``request_bars(update_catalog=True)`` then serves history from the catalog and
    tops up only the missing IBKR tail, so research and live warm from the *same*
    corpus with no cold-start lookback gap.  Broker and Custom Data client configs
    are supplied through this public config surface before the node is constructed;
    only their factories are registered afterward.

    An unexpected exception in the live RiskEngine's message queue shuts the node
    down gracefully rather than leaving pre-trade risk processing uncertain.

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
        risk_engine=LiveRiskEngineConfig(graceful_shutdown_on_exception=True),
        cache=CacheConfig(),
        logging=LoggingConfig(),
        catalogs=[DataCatalogConfig(path=str(catalog_root()))],
        # Quote-marked legs are valued at the strategy-published quote mid
        # (aegis-rd-tggo.3); bar-marked legs fall back to their bar close.
        portfolio=PortfolioConfig(use_mark_prices=use_mark_prices),
        data_clients=dict(data_clients or {}),
        exec_clients=dict(exec_clients or {}),
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
    custom_data_providers: CustomDataAdapterMap | None = None,
    custom_data_registry: CustomDataRegistry | None = None,
) -> TradingNode:
    """Assemble a built, runnable live ``TradingNode`` for *book* over *connection*.

    Loads the book's sleeves, derives the InstrumentProvider ``load_ids`` from the
    union of their declared native ids, wires IBKR's stock clients/factories via
    the single broker seam, builds the node, and adds the strategy.  Paper vs live
    is decided entirely by ``connection`` (its port).
    """
    registry = registry if registry is not None else EntryPointBundleRegistry()
    custom_data_providers = custom_data_providers or {}
    assembled_book = assemble_book(
        book,
        registry,
        custom_data_registry=custom_data_registry,
    )

    # The bundle-recorded markings are the live marking truth (aegis-rd-tggo.3):
    # built once here, they decide both the strategy's subscriptions and whether
    # the Portfolio values quote-marked legs at the published mid.
    marking_resolver = recorded_marking_resolver(assembled_book)
    broker_clients = live_clients(
        connection,
        assembled_book.loadable_instrument_ids,
    )
    streaming = live_custom_data(
        custom_data_providers,
        registry=custom_data_registry,
        configured_client_names=broker_clients.data_clients,
    )
    node = TradingNode(
        config=build_live_node_config(
            trader_id=connection.trader_id,
            use_mark_prices=bool(marking_resolver.quote_marked_ids),
            data_clients={**broker_clients.data_clients, **streaming.data_clients},
            exec_clients=broker_clients.exec_clients,
        )
    )
    catalog = open_catalog(catalog_root())
    broker_clients.register(node)
    streaming.register(
        node,
        catalog=catalog,
        registry=custom_data_registry,
    )
    arrays = build_live_sleeve_arrays(
        custom_data_providers,
        catalog=catalog,
        registry=custom_data_registry,
    )
    warm_live_custom_data(
        assembled_book,
        arrays,
        now=datetime.now(timezone.utc),
    )
    node.build()
    node.trader.add_strategy(
        build_live_strategy(
            assembled_book,
            arrays=arrays,
            catalog=catalog,
        )
    )
    return node


def build_live_strategy(
    book: AssembledBook,
    *,
    arrays: SleeveArrays,
    catalog: Catalog,
) -> RebalanceStrategy:
    """The live ``RebalanceStrategy`` for *book*: next-close ``AT_THE_CLOSE`` and
    cache warmup on start, with the assembled book registered.

    The bar-type resolver is the bundle-recorded marking view — live subscribes
    exactly the mark research validated and fails closed on an unrecorded leg.
    """
    strategy = RebalanceStrategy(
        RebalanceStrategyConfig(
            book=book.config,
            fill_time_in_force=LIVE_FILL_TIME_IN_FORCE,
            warmup_cache_on_start=True,
            capture_bars=True,
        ),
        arrays=arrays,
        catalog=catalog,
        bar_type_resolver=recorded_marking_resolver(book),
    )
    strategy.register_book(book)
    return strategy


# ── run / stop lifecycle ──────────────────────────────────────────────────────


def start_trader(
    book_path: str | Path,
    connection: IBConnectionSettings,
    *,
    pid_file: Path | None = None,
    registry: BundleRegistryPort | None = None,
    recovery_handler: Callable[[RecoveryUpdate], None] | None = None,
) -> int:
    """Build and run the live trader for the book at *book_path* in the foreground.

    The pidfile is taken *first*, so a second trader is refused before it reaches
    the broker: attaching a duplicate client to IBKR only to discover the book is
    already being traded costs a connection attempt and reports the wrong fault.
    """
    with _held_pid_file(pid_file or default_pid_file()):
        book = load_book_config(book_path)
        node = build_live_node(book, connection, registry=registry)
        if recovery_handler is not None:
            node.kernel.msgbus.subscribe(RECOVERY_TOPIC, recovery_handler)
        return run_node(node)


def run_node(node: TradingNode) -> int:
    """Run *node* in the foreground until stopped, then dispose — the Nautilus
    canonical shutdown.

    Nautilus's kernel installs the SIGTERM/SIGINT loop handlers itself (they call
    ``node.stop()``), so on a delivered signal ``node.run()`` returns and the
    ``finally`` tears the node down; the ``except KeyboardInterrupt`` is the
    canonical safety net for a Ctrl-C before the loop is running.  The pidfile
    ``trader stop`` signals is held by :func:`start_trader` around this call.

    Exits non-zero when the node shut *itself* down.  A stop we asked for — a
    delivered signal or Ctrl-C — reaches the kernel directly, so only a
    self-shutdown publishes ``ShutdownSystem``; that is what the live engines
    raise on an unhandled exception, and the supervisor must see it as a failure
    rather than as the clean stop a bare ``0`` would claim.
    """
    self_shutdowns: list[ShutdownSystem] = []
    _watch_self_shutdown(node, self_shutdowns.append)
    try:
        node.run()
    except KeyboardInterrupt:
        _log.info("Interrupt received; stopping the trader")
    finally:
        try:
            node.stop()
        finally:
            node.dispose()
    for command in self_shutdowns:
        _log.error(
            "Trader shut itself down (%s): %s", command.component_id, command.reason
        )
    return 1 if self_shutdowns else 0


def _watch_self_shutdown(
    node: TradingNode, record: Callable[[ShutdownSystem], None]
) -> None:
    """Record every self-initiated shutdown of *node* as it is commanded."""
    node.kernel.msgbus.subscribe("commands.system.shutdown", record)


def stop_trader(*, pid_file: Path | None = None) -> int:
    """Stop a running live trader: read its pidfile and send ``SIGTERM``.

    A pidfile outlives a hard termination, so the PID it names is only acted on
    while its writer still holds the file's lock; an unheld pidfile is stale and
    is cleared and reported as "not running" rather than signalled.
    """
    target = pid_file or default_pid_file()
    pid = _running_trader_pid(target)
    os.kill(pid, signal.SIGTERM)
    _log.info("Sent SIGTERM to trader pid %d (%s)", pid, target)
    return 0


def default_pid_file() -> Path:
    """The default pidfile in the per-user runtime dir (``--pid-file`` overrides)."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime_dir) if runtime_dir else Path(tempfile.gettempdir())
    return base / _PID_FILE_NAME


@contextmanager
def _held_pid_file(pid_file: Path) -> Iterator[None]:
    """Hold *pid_file* locked for the duration, and clear it on the way out.

    The lock is what makes a pidfile trustworthy.  A pidfile survives any hard
    termination — ``os._exit``, ``SIGKILL``, an OOM kill — and PIDs are recycled,
    so the number alone can name an unrelated live process.  The kernel drops
    this lock however the holder dies, so an unheld pidfile is provably stale,
    with nothing to parse and no liveness to infer.

    Taking it also makes a second trader on the same pidfile impossible rather
    than merely unlikely.
    """
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    handle = pid_file.open("a+")
    try:
        if not _lock_acquired(handle):
            raise TraderAlreadyRunningError(
                f"another trader already holds {pid_file}; stop it before starting a new one"
            )
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        handle.close()  # releases the lock
        pid_file.unlink(missing_ok=True)


def _running_trader_pid(pid_file: Path) -> int:
    """The PID of the trader currently holding *pid_file*.

    Taking the lock proves nobody holds it, which means the pidfile outlived its
    writer; it is then cleared rather than acted on, so a recycled PID is never
    signalled.
    """
    try:
        handle = pid_file.open("r+")
    except FileNotFoundError as exc:
        raise TraderNotRunningError(
            f"no trader pidfile at {pid_file}; is the trader running?"
        ) from exc
    with handle:
        if _lock_acquired(handle):
            pid_file.unlink(missing_ok=True)
            raise TraderNotRunningError(
                f"trader pidfile {pid_file} is stale — no live process holds it; "
                f"removed it without signalling"
            )
        raw = handle.read()
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise TraderNotRunningError(
            f"trader pidfile {pid_file} is malformed: {raw!r}"
        ) from exc


def _lock_acquired(handle: IO[str]) -> bool:
    """Whether this process could take *handle*'s exclusive lock without waiting."""
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True
