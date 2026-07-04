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
from types import SimpleNamespace

import pytest
from nautilus_trader.common import Environment
from nautilus_trader.config import (
    CacheConfig,
    LiveDataEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import catalog_root
from aegis_runtime import DataContract, MissingIndexPolicy

from aegis_trader.bundles.book_sleeves import (
    load_book_sleeves,
    union_loadable_instrument_ids,
)
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.config import IBConnectionSettings
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.node import (
    LIVE_FILL_TIME_IN_FORCE,
    TraderNotRunningError,
    build_live_node_config,
    build_live_risk_engine_config,
    build_live_strategy,
    default_pid_file,
    run_node,
    stop_trader,
)


def _book() -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0
            ),
        ),
        base_currency="EUR",
    )


def _contract(*ids: str) -> DataContract:
    return DataContract(
        instrument_ids=tuple(InstrumentId.from_str(i) for i in ids),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
    )


# --------------------------------------------------------------------------- #
# live next-close TIF (ADR-0001)
# --------------------------------------------------------------------------- #


def test_live_fill_time_in_force_is_market_on_close():
    """Live carries AT_THE_CLOSE (Market-on-Close into the auction); the backtest
    counterpart is a plain MARKET (``None``)."""
    assert LIVE_FILL_TIME_IN_FORCE == TimeInForce.AT_THE_CLOSE


# --------------------------------------------------------------------------- #
# live RiskEngine wiring
# --------------------------------------------------------------------------- #


def test_live_risk_engine_config_carries_rate_limits_and_is_not_bypassed():
    cfg = build_live_risk_engine_config()
    assert cfg.bypass is False
    assert cfg.max_order_submit_rate == "10/00:00:01"
    assert cfg.max_order_modify_rate == "10/00:00:01"


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


def test_live_node_config_wires_the_live_risk_engine():
    cfg = build_live_node_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False


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
# instrument-id (load_ids) derivation
# --------------------------------------------------------------------------- #


def test_union_loadable_instrument_ids_unions_and_sorts_declared_natives():
    """``load_ids`` is the sorted union of the bundles' loadable ids — the
    data-only FX ``exchange:`` conversion legs ride in alongside the tradeable
    natives (aegis-rd-reyj), with no construction or currency derivation."""
    fx_contract = DataContract(
        instrument_ids=(InstrumentId.from_str("VUSA.XLON"),),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
        exchange=(InstrumentId.from_str("EUR/USD.IDEALPRO"),),
    )
    sleeves = (
        (SleeveName("equity"), SimpleNamespace(contract=_contract("VUSA.XLON"))),
        (SleeveName("fx_overlay"), SimpleNamespace(contract=fx_contract)),
    )

    ids = union_loadable_instrument_ids(sleeves)

    assert [i.value for i in ids] == ["EUR/USD.IDEALPRO", "VUSA.XLON"]


def test_union_loadable_instrument_ids_excludes_continuous_future_roots():
    """A continuous-future root is declared on ``DataContract.futures``, not loaded as a
    static native: its legs arrive dynamically via the chain.  The union (the node's
    ``load_ids``) must carry only the declared native ids, never the bare roots."""
    contract = DataContract(
        instrument_ids=(
            InstrumentId.from_str("VUSA.XLON"),
            InstrumentId.from_str("ES.XCME"),
        ),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
        futures=("ES",),
    )
    sleeves = ((SleeveName("equity"), SimpleNamespace(contract=contract)),)

    ids = union_loadable_instrument_ids(sleeves)

    # The continuous id ES.XCME (matching root ES) is excluded; only the true native rides.
    assert [i.value for i in ids] == ["VUSA.XLON"]


def test_load_book_sleeves_resolves_each_sleeve_via_the_registry():
    book = _book()
    bundle = SimpleNamespace(contract=_contract("VUSA.XLON"))
    registry = StubBundleRegistry({"trend.whl": bundle})

    sleeves = load_book_sleeves(book, registry)

    assert sleeves == ((SleeveName("trend"), bundle),)


# --------------------------------------------------------------------------- #
# live strategy assembly
# --------------------------------------------------------------------------- #


def test_build_live_strategy_carries_at_the_close_warmup_and_registered_sleeves():
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
    sleeves = (
        (SleeveName("trend"), SimpleNamespace(contract=_contract("VUSA.XLON"))),
        (
            SleeveName("fx_overlay"),
            SimpleNamespace(contract=_contract("EUR/USD.IDEALPRO", "VUSA.XLON")),
        ),
    )

    strategy = build_live_strategy(book, sleeves)
    registered_ids = strategy._registered_instrument_ids()

    assert strategy.config.fill_time_in_force == TimeInForce.AT_THE_CLOSE
    assert strategy.config.warmup_cache_on_start is True
    assert registered_ids == (
        InstrumentId.from_str("EUR/USD.IDEALPRO"),
        InstrumentId.from_str("VUSA.XLON"),
    )
    assert registered_ids == union_loadable_instrument_ids(sleeves)


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
        port=4002, client_id=9,
        account_id="DU1234567", trader_id="BOOK-EU-01",
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
    assert set(execution.instrument_provider.load_ids) == set(data.instrument_provider.load_ids)
    assert node.data_factories[IB_CLIENT_NAME] is InteractiveBrokersLiveDataClientFactory
    assert node.exec_factories[IB_CLIENT_NAME] is InteractiveBrokersLiveExecClientFactory


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
        port=4002, client_id=9,
        account_id="DU1234567", trader_id="BOOK-EU-01",
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


class _FakeRunNode:
    """Stand-in TradingNode capturing the run/stop/dispose ordering."""

    def __init__(self, *, interrupt: bool = False) -> None:
        self.events: list[str] = []
        self._interrupt = interrupt

    def run(self) -> None:
        self.events.append("run")
        if self._interrupt:
            raise KeyboardInterrupt

    def stop(self) -> None:
        self.events.append("stop")

    def dispose(self) -> None:
        self.events.append("dispose")


def test_run_node_runs_then_stops_disposes_and_clears_pidfile(tmp_path):
    node = _FakeRunNode()
    pid_file = tmp_path / "trader.pid"

    rc = run_node(node, pid_file=pid_file)

    assert rc == 0
    assert node.events == ["run", "stop", "dispose"]
    assert not pid_file.exists()


def test_run_node_writes_the_current_pid_before_running(tmp_path):
    pid_file = tmp_path / "trader.pid"
    seen: dict[str, str] = {}

    class _Node(_FakeRunNode):
        def run(self) -> None:
            seen["pid"] = pid_file.read_text()
            super().run()

    run_node(_Node(), pid_file=pid_file)

    assert seen["pid"] == str(os.getpid())


def test_run_node_shuts_down_gracefully_on_keyboard_interrupt(tmp_path):
    """Ctrl-C / SIGINT before the loop is running surfaces as KeyboardInterrupt;
    the node still stops then disposes (the Nautilus-correct shutdown)."""
    node = _FakeRunNode(interrupt=True)
    pid_file = tmp_path / "trader.pid"

    rc = run_node(node, pid_file=pid_file)

    assert rc == 0
    assert node.events == ["run", "stop", "dispose"]
    assert not pid_file.exists()


def test_stop_trader_sends_sigterm_to_the_pidfile_pid(tmp_path, monkeypatch):
    pid_file = tmp_path / "trader.pid"
    pid_file.write_text("4321")
    sent: dict[str, int] = {}
    monkeypatch.setattr(
        "aegis_trader.trader.node.os.kill",
        lambda pid, sig: sent.update(pid=pid, sig=sig),
    )

    rc = stop_trader(pid_file=pid_file)

    assert rc == 0
    assert sent == {"pid": 4321, "sig": signal.SIGTERM}


def test_stop_trader_fails_closed_when_no_pidfile(tmp_path):
    with pytest.raises(TraderNotRunningError):
        stop_trader(pid_file=tmp_path / "missing.pid")


def test_default_pid_file_lives_in_the_per_user_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert default_pid_file() == tmp_path / "aegis-trader.pid"
