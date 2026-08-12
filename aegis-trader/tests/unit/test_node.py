"""Unit tests for the live trading node (aegis-rd-r8b.8).

Covers the broker-neutral live-node config, the live strategy assembly, the
instrument-id (``load_ids``) derivation, and the ``trader start``/``stop``
lifecycle (run loop, pidfile, signal handling) — all without a live IBKR
connection.  The IBKR client wiring (:func:`attach_live_clients`) needs ``ibapi``
and is exercised separately (``importorskip``); the broker-neutral surface here
must not pull ``ibapi`` at all (the lazy-import invariant).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

import msgspec
import pytest
from nautilus_trader.common import Environment
from nautilus_trader.common.messages import ShutdownSystem
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.config import (
    CacheConfig,
    LiveDataEngineConfig,
    LiveDataClientConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import ComponentId, InstrumentId, TraderId

from aegis_data.catalog import catalog_root
from aegis_data.storage import Catalog

from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.config import IBConnectionSettings
from aegis_trader.bundles.bands import InstrumentBandError
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.node import (
    LIVE_FILL_TIME_IN_FORCE,
    TraderAlreadyRunningError,
    TraderNotRunningError,
    _held_pid_file,
    build_live_node_config,
    build_live_node,
    build_live_strategy,
    default_pid_file,
    run_node,
    start_trader,
    stop_trader,
)
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from tests.support.factories import assemble_test_book, make_bundle


def _book() -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0
            ),
        ),
        base_currency="EUR",
    )


# --------------------------------------------------------------------------- #
# live next-close TIF (ADR-0001)
# --------------------------------------------------------------------------- #


def test_live_fill_time_in_force_is_market_on_close():
    """Live carries AT_THE_CLOSE (Market-on-Close into the auction); the backtest
    counterpart is a plain MARKET (``None``)."""
    assert LIVE_FILL_TIME_IN_FORCE == TimeInForce.AT_THE_CLOSE


# --------------------------------------------------------------------------- #
# broker-neutral live node config (no IBKR vocabulary, no ibapi)
# --------------------------------------------------------------------------- #


def test_live_node_config_runs_under_live_environment():
    cfg = build_live_node_config()
    assert cfg.environment == Environment.LIVE


def test_live_node_config_wires_cache_logging_and_reconciliation():
    cfg = build_live_node_config()
    assert isinstance(cfg.cache, CacheConfig)
    assert isinstance(cfg.logging, LoggingConfig)
    assert cfg.exec_engine.reconciliation is True


def test_live_node_config_uses_nautilus_risk_defaults_with_graceful_shutdown():
    """Pin the upstream defaults and Aegis's live-only shutdown policy."""
    cfg = build_live_node_config()
    risk = cfg.risk_engine

    assert type(risk) is LiveRiskEngineConfig
    assert risk.bypass is False
    assert risk.max_order_submit_rate == "100/00:00:01"
    assert risk.max_order_modify_rate == "100/00:00:01"
    assert risk.graceful_shutdown_on_exception is True


def test_live_node_config_wires_the_shared_catalog():
    """Reads the same shared aegis-data catalog as research (ADR-0006): startup
    request_bars serves history from it and persists the IBKR tail."""
    cfg = build_live_node_config()
    assert [c.path for c in cfg.catalogs] == [str(catalog_root())]


def test_live_node_config_disables_time_bars_build_with_no_updates():
    """AC6 confirm (r8b.9 Slice F(c)).  Under Model 2 the continuous series is materialised
    off-cache by the feed, so the node only subscribes each root's **raw front leg**
    (execution + the feed's daily wake).  That daily subscription inherits
    ``DataEngineConfig``'s ``time_bars_build_with_no_updates=True`` default, which emits
    non-trading-day flat bars → spurious wakes/stale marks; the live node must keep it off
    (prototype NOTES.md V5 CONFIG finding)."""
    cfg = build_live_node_config()
    assert isinstance(cfg.data_engine, LiveDataEngineConfig)
    assert cfg.data_engine.time_bars_build_with_no_updates is False


def test_live_node_config_carries_the_trader_id():
    cfg = build_live_node_config(trader_id="BOOK-EU-01")
    assert cfg.trader_id.value == "BOOK-EU-01"


def test_live_node_config_is_msgspec_serializable():
    cfg = build_live_node_config()
    loaded = TradingNodeConfig.parse(cfg.json())
    assert loaded.environment == cfg.environment
    assert loaded.exec_engine.reconciliation is True


def test_importing_the_node_module_does_not_import_ibapi():
    """The broker-neutral invariant: importing ``trader.node`` (and the IBKR
    adapter it reaches) must not eagerly import ``ibapi`` — checked in a fresh
    interpreter so an unrelated test's ``ibapi`` import cannot mask a regression."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import aegis_trader.trader.node, sys; "
            "sys.exit(1 if 'ibapi' in sys.modules else 0)",
        ],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()


# --------------------------------------------------------------------------- #
# live strategy assembly
# --------------------------------------------------------------------------- #


def test_build_live_strategy_carries_at_the_close_warmup_and_registered_sleeves(
    tmp_path,
):
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=0.5
            ),
            SleeveConfig(
                name=SleeveName("fx_overlay"),
                wheel_filename="fx_overlay.whl",
                risk_share=0.5,
            ),
        ),
        base_currency="EUR",
    )
    vusa = InstrumentId.from_str("VUSA.XLON")
    eurusd = InstrumentId.from_str("EUR/USD.IDEALPRO")
    msft = InstrumentId.from_str("MSFT.NASDAQ")
    assembled = assemble_test_book(
        book,
        {
            "trend.whl": make_bundle(native_instrument_ids=(vusa,)),
            "fx_overlay.whl": make_bundle(
                native_instrument_ids=(msft,),
                exchange_instrument_ids=(eurusd,),
            ),
        },
    )

    strategy = build_live_strategy(
        assembled,
        arrays=SleeveArrays.bar_only(),
        catalog=Catalog.open(tmp_path),
    )

    assert strategy.config.fill_time_in_force == TimeInForce.AT_THE_CLOSE
    assert strategy.config.warmup_cache_on_start is True


def test_build_live_node_rejects_an_invalid_book_before_broker_attachment(
    monkeypatch,
) -> None:
    trend = SleeveName("trend")
    carry = SleeveName("carry")
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=trend, wheel_filename="trend.whl", risk_share=0.5),
            SleeveConfig(name=carry, wheel_filename="carry.whl", risk_share=0.5),
        )
    )
    shared_instrument = InstrumentId.from_str("MSFT.NASDAQ")
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(native_instrument_ids=(shared_instrument,)),
            "carry.whl": make_bundle(native_instrument_ids=(shared_instrument,)),
        }
    )
    broker_attachments: list[object] = []
    monkeypatch.setattr(
        "aegis_trader.trader.node.attach_live_clients",
        lambda *args: broker_attachments.append(args),
    )
    connection = IBConnectionSettings(
        port=4002,
        client_id=9,
        account_id="DU1234567",
        trader_id="BOOK-EU-01",
    )

    with pytest.raises(InstrumentBandError):
        build_live_node(book, connection, registry=registry)

    assert broker_attachments == []


def test_build_live_node_adds_custom_clients_after_broker_and_before_build(
    monkeypatch,
) -> None:
    events: list[str] = []

    attached_arrays: list[object] = []
    arrays = object()

    class _Trader:
        def add_strategy(self, strategy: object) -> None:
            events.append("strategy")

    class _BuiltNode:
        def __init__(self, *, config: TradingNodeConfig) -> None:
            self._config = config
            self.trader = _Trader()

        def build(self) -> None:
            events.append("build")

    def build_strategy(
        _book: object,
        *,
        arrays: object,
        catalog: object,
    ) -> object:
        attached_arrays.append(arrays)
        attached_arrays.append(catalog)
        return object()

    def build_arrays(*args, **kwargs) -> object:
        events.append("arrays")
        return arrays

    monkeypatch.setattr("aegis_trader.trader.node.TradingNode", _BuiltNode)
    monkeypatch.setattr(
        "aegis_trader.trader.node.attach_live_clients",
        lambda *args: events.append("broker"),
    )
    monkeypatch.setattr(
        "aegis_trader.trader.node.add_live_custom_data",
        lambda *args, **kwargs: events.append("custom"),
    )
    monkeypatch.setattr(
        "aegis_trader.trader.node.build_live_sleeve_arrays",
        build_arrays,
    )
    monkeypatch.setattr(
        "aegis_trader.trader.node.warm_live_custom_data",
        lambda *args, **kwargs: events.append("warm"),
    )
    monkeypatch.setattr(
        "aegis_trader.trader.node.build_live_strategy",
        build_strategy,
    )
    instrument_id = InstrumentId.from_str("VUSA.XLON")
    registry = StubBundleRegistry(
        {"trend.whl": make_bundle(native_instrument_ids=(instrument_id,))}
    )
    connection = IBConnectionSettings(
        port=4002,
        client_id=9,
        account_id="DU1234567",
        trader_id="BOOK-EU-01",
    )

    build_live_node(
        _book(),
        connection,
        registry=registry,
        custom_data_providers={},
    )

    assert events == [
        "broker",
        "custom",
        "arrays",
        "warm",
        "build",
        "strategy",
    ]
    assert attached_arrays[0] is arrays
    assert isinstance(attached_arrays[1], Catalog)


# --------------------------------------------------------------------------- #
# IBKR live client wiring (needs ibapi — exercised here, not in aegis-data)
# --------------------------------------------------------------------------- #


class _FakeNode:
    """Records factory registration and holds a swappable config — stands in for
    ``TradingNode`` so the wiring is checked without an event loop or IB client."""

    def __init__(self, config: TradingNodeConfig) -> None:
        self._config = config
        self.data_factories: dict[str, object] = {}
        self.exec_factories: dict[str, object] = {}

    def add_data_client_factory(self, name: str, factory: object) -> None:
        self.data_factories[name] = factory

    def add_exec_client_factory(self, name: str, factory: object) -> None:
        self.exec_factories[name] = factory


def test_attach_live_clients_wires_stock_ibkr_clients_and_factories():
    pytest.importorskip("ibapi")
    from nautilus_trader.adapters.interactive_brokers.config import IBMarketDataTypeEnum
    from nautilus_trader.adapters.interactive_brokers.factories import (
        InteractiveBrokersLiveDataClientFactory,
        InteractiveBrokersLiveExecClientFactory,
    )

    from aegis_data.ibkr import IB_CLIENT_NAME, attach_live_clients

    node = _FakeNode(build_live_node_config(trader_id="BOOK-EU-01"))
    connection = IBConnectionSettings(
        port=4002,
        client_id=9,
        account_id="DU1234567",
        trader_id="BOOK-EU-01",
    )
    instrument_ids = (
        InstrumentId.from_str("VUSA.XLON"),
        InstrumentId.from_str("EUR/USD.IDEALPRO"),
    )

    attach_live_clients(node, connection, instrument_ids)

    data = node._config.data_clients[IB_CLIENT_NAME]
    execution = node._config.exec_clients[IB_CLIENT_NAME]
    assert data.market_data_type == IBMarketDataTypeEnum.REALTIME
    # Nautilus requires the default localhost host with DockerizedIBGatewayConfig;
    # the gateway-owned port remains unset until the factory starts/reuses it.
    assert (data.ibg_host, data.ibg_port, data.ibg_client_id) == ("127.0.0.1", None, 9)
    assert data.dockerized_gateway.trading_mode == "paper"
    assert data.dockerized_gateway.read_only_api is False
    assert execution.dockerized_gateway == data.dockerized_gateway
    assert set(data.instrument_provider.load_ids) == {"VUSA.XLON", "EUR/USD.IDEALPRO"}
    assert execution.account_id == "DU1234567"
    assert set(execution.instrument_provider.load_ids) == set(
        data.instrument_provider.load_ids
    )
    assert (
        node.data_factories[IB_CLIENT_NAME] is InteractiveBrokersLiveDataClientFactory
    )
    assert (
        node.exec_factories[IB_CLIENT_NAME] is InteractiveBrokersLiveExecClientFactory
    )


def test_attach_live_clients_preserves_an_existing_data_client():
    pytest.importorskip("ibapi")
    from aegis_data.ibkr import attach_live_clients

    fixture_config = LiveDataClientConfig()
    node = _FakeNode(
        msgspec.structs.replace(
            build_live_node_config(trader_id="BOOK-EU-01"),
            data_clients={"FIXTURE": fixture_config},
        )
    )

    attach_live_clients(
        node,
        IBConnectionSettings(
            port=4002,
            client_id=9,
            account_id="DU1234567",
            trader_id="BOOK-EU-01",
        ),
        (InstrumentId.from_str("VUSA.XLON"),),
    )

    assert node._config.data_clients["FIXTURE"] is fixture_config


def test_attach_live_clients_pins_mic_venues():
    """Slice F(b) — ICE/CME venue-symbology pin.

    The continuous-root id is ``{root}.{venue}`` and aegis-data's chain build rejects legs
    spanning >1 venue, so the venue IBKR contracts resolve to must be ONE deterministic form.
    The gateway probe (bd ``resolved-r8b-9-probe6-ice-venue``) showed the stock IBKR provider
    defaults to the raw exchange (``CME`` / ``NYBOT``); ``convert_exchange_to_mic_venue=True``
    flips it to the MIC form (``XCME`` / ``IFUS``) the catalog + continuous goldens use. Both
    the data and exec instrument providers must carry the pin."""
    pytest.importorskip("ibapi")
    from aegis_data.ibkr import IB_CLIENT_NAME, attach_live_clients

    node = _FakeNode(build_live_node_config(trader_id="BOOK-EU-01"))
    connection = IBConnectionSettings(
        port=4002,
        client_id=9,
        account_id="DU1234567",
        trader_id="BOOK-EU-01",
    )

    attach_live_clients(node, connection, (InstrumentId.from_str("VUSA.XLON"),))

    data = node._config.data_clients[IB_CLIENT_NAME]
    execution = node._config.exec_clients[IB_CLIENT_NAME]
    assert data.instrument_provider.convert_exchange_to_mic_venue is True
    assert execution.instrument_provider.convert_exchange_to_mic_venue is True


def test_historic_provider_config_pins_mic_venues():
    """Slice F(b) — the seed/backfill path qualifies IBKR exchanges to MIC venues too, so
    seeded catalog ids carry ``{root}.XCME`` / ``.IFUS`` (the form aegis-data's continuous
    chain expects). The live and historic providers share one pinned config."""
    pytest.importorskip("ibapi")
    from aegis_data.ibkr import mic_instrument_provider_config

    config = mic_instrument_provider_config()
    assert config.convert_exchange_to_mic_venue is True


# --------------------------------------------------------------------------- #
# run / stop lifecycle
# --------------------------------------------------------------------------- #


class _FakeMsgBus:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def subscribe(self, topic: str, handler) -> None:
        self.handlers[topic] = handler


class _FakeKernel:
    def __init__(self) -> None:
        self.msgbus = _FakeMsgBus()


class _FakeRunNode:
    """Stand-in TradingNode capturing the run/stop/dispose ordering."""

    def __init__(self, *, interrupt: bool = False, self_shutdown: str | None = None) -> None:
        self.events: list[str] = []
        self._interrupt = interrupt
        self._self_shutdown = self_shutdown
        self.kernel = _FakeKernel()

    def run(self) -> None:
        self.events.append("run")
        if self._self_shutdown is not None:
            # What the live engines do on an unhandled exception.
            self.kernel.msgbus.handlers["commands.system.shutdown"](
                ShutdownSystem(
                    trader_id=TraderId("TESTER-000"),
                    component_id=ComponentId("RiskEngine"),
                    reason=self._self_shutdown,
                    command_id=UUID4(),
                    ts_init=0,
                )
            )
        if self._interrupt:
            raise KeyboardInterrupt

    def stop(self) -> None:
        self.events.append("stop")

    def dispose(self) -> None:
        self.events.append("dispose")


def test_run_node_runs_then_stops_and_disposes(tmp_path):
    node = _FakeRunNode()

    rc = run_node(node)

    assert rc == 0
    assert node.events == ["run", "stop", "dispose"]


def test_run_node_exits_non_zero_when_the_node_shuts_itself_down():
    """A self-shutdown is a failure, not the clean stop a bare 0 would claim.

    With graceful shutdown enabled, an unhandled exception in a live engine stops
    the node tidily — so the exit code is the only thing left that tells the
    supervisor something went wrong.
    """
    node = _FakeRunNode(self_shutdown="Unexpected exception in RiskEngine queue")

    rc = run_node(node)

    assert rc == 1
    assert node.events == ["run", "stop", "dispose"]


def test_run_node_exits_zero_for_a_stop_we_asked_for():
    """A delivered signal reaches the kernel directly and publishes no command."""
    assert run_node(_FakeRunNode()) == 0


def test_run_node_shuts_down_gracefully_on_keyboard_interrupt():
    """Ctrl-C / SIGINT before the loop is running surfaces as KeyboardInterrupt;
    the node still stops then disposes (the Nautilus-correct shutdown)."""
    node = _FakeRunNode(interrupt=True)

    rc = run_node(node)

    assert rc == 0
    assert node.events == ["run", "stop", "dispose"]


def test_start_trader_records_its_pid_while_running(tmp_path, monkeypatch):
    pid_file = tmp_path / "trader.pid"
    seen: dict[str, str] = {}
    node = _FakeRunNode()

    monkeypatch.setattr("aegis_trader.trader.node.load_book_config", lambda path: None)
    monkeypatch.setattr(
        "aegis_trader.trader.node.build_live_node", lambda *a, **k: node
    )
    monkeypatch.setattr(
        node, "run", lambda: seen.update(pid=pid_file.read_text())
    )

    rc = start_trader("book.toml", object(), pid_file=pid_file)

    assert rc == 0
    assert seen["pid"] == str(os.getpid())
    assert not pid_file.exists()


def test_start_trader_refuses_a_held_pidfile_before_reaching_the_broker(
    tmp_path, monkeypatch
):
    """A second trader must be refused before it attaches a duplicate IBKR client.

    Discovering the clash only after connecting costs a connection attempt and
    reports a broker fault instead of the plain "already running" it is.
    """
    pid_file = tmp_path / "trader.pid"
    reached: list[str] = []
    monkeypatch.setattr(
        "aegis_trader.trader.node.load_book_config",
        lambda path: reached.append("loaded the book"),
    )
    monkeypatch.setattr(
        "aegis_trader.trader.node.build_live_node",
        lambda *a, **k: reached.append("reached the broker"),
    )

    with _held_pid_file(pid_file):
        with pytest.raises(TraderAlreadyRunningError):
            start_trader("book.toml", object(), pid_file=pid_file)

    assert reached == []


def test_stop_trader_sends_sigterm_to_the_pid_holding_the_pidfile(tmp_path, monkeypatch):
    """A held pidfile names a live trader, so its PID is signalled."""
    pid_file = tmp_path / "trader.pid"
    sent: dict[str, int] = {}
    monkeypatch.setattr(
        "aegis_trader.trader.node.os.kill",
        lambda pid, sig: sent.update(pid=pid, sig=sig),
    )

    with _held_pid_file(pid_file):
        rc = stop_trader(pid_file=pid_file)

    assert rc == 0
    assert sent == {"pid": os.getpid(), "sig": signal.SIGTERM}


def test_stop_trader_fails_closed_when_no_pidfile(tmp_path):
    with pytest.raises(TraderNotRunningError):
        stop_trader(pid_file=tmp_path / "missing.pid")


def test_stop_trader_refuses_an_unheld_pidfile_whose_pid_may_be_recycled(
    tmp_path, monkeypatch
):
    """A pidfile outliving a hard kill can name a live, unrelated process.

    No process holds the lock, so the trader is reported not running and the
    recycled PID is never signalled.
    """
    pid_file = tmp_path / "trader.pid"
    pid_file.write_text(str(os.getpid()))  # our own live PID, but nobody holds the file
    monkeypatch.setattr(
        "aegis_trader.trader.node.os.kill",
        lambda pid, sig: pytest.fail(f"signalled unheld pid {pid}"),
    )

    with pytest.raises(TraderNotRunningError):
        stop_trader(pid_file=pid_file)


def test_stop_trader_clears_the_stale_pidfile_it_refused(tmp_path):
    pid_file = tmp_path / "trader.pid"
    pid_file.write_text(str(os.getpid()))

    with pytest.raises(TraderNotRunningError):
        stop_trader(pid_file=pid_file)

    assert not pid_file.exists()


def test_a_second_trader_cannot_take_a_held_pidfile(tmp_path):
    """The lock makes two traders on one pidfile impossible, not merely unlikely."""
    pid_file = tmp_path / "trader.pid"

    with _held_pid_file(pid_file):
        with pytest.raises(TraderAlreadyRunningError):
            with _held_pid_file(pid_file):
                pytest.fail("a second trader took a held pidfile")


def test_run_node_releases_the_pidfile_for_the_next_trader(tmp_path):
    """A clean run leaves nothing behind that would block a restart."""
    pid_file = tmp_path / "trader.pid"

    with _held_pid_file(pid_file):
        pass
    with _held_pid_file(pid_file):
        pass

    assert not pid_file.exists()


def test_default_pid_file_lives_in_the_per_user_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert default_pid_file() == tmp_path / "aegis-trader.pid"
