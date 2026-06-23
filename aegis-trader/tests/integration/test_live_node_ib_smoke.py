"""Layer 2 — real live TradingNode liveness on the IB paper gateway (r8b.9 .5, env-gated).

Connects the actual broker-neutral live ``TradingNode`` (real IB live data + exec clients via the
single ``attach_live_clients`` seam) to a running gateway and asserts the LIVE data client's
``request_instrument → on_instrument`` round-trips on the running node — the dynamic-leg-load path
(Slice G) on the real adapter, distinct from the historical client exercised in
``test_ibkr_provider_live`` and complementary to the deterministic live-engine golden in
``test_live_node_roll``.

Gated on ``IB_PORT`` + ``IB_ACCOUNT_ID`` (the node reconciles the exec account), so it is skipped
in CI and runs only against an operator's gateway.  No module-level ``importorskip('ibapi')`` —
ibapi is imported lazily inside ``attach_live_clients`` only when a test runs, keeping collection
ibapi-free (the lazy-import guard).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress

import pytest
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.test_kit.functions import eventually
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_data.ibkr import attach_live_clients
from aegis_trader.config.connection import IBConnectionSettings
from aegis_trader.trader.node import build_live_node_config

_PORT = os.environ.get("IB_PORT")
_ACCOUNT = os.environ.get("IB_ACCOUNT_ID")
# An active dated ES quarterly leg (a real roll loads exactly this kind of leg at runtime).
_LEG = InstrumentId.from_str("ESU6.XCME")

pytestmark = pytest.mark.skipif(
    not (_PORT and _ACCOUNT),
    reason="set IB_PORT + IB_ACCOUNT_ID to run against a live IB Gateway",
)


class _ProbeConfig(StrategyConfig, frozen=True):
    pass


class _InstrumentLoadProbe(Strategy):
    """Minimal strategy: on start it dynamically loads a dated leg via the live data client (the
    Slice G path) and records the leg delivered to ``on_instrument``."""

    def __init__(self, config: _ProbeConfig) -> None:
        super().__init__(config)
        self.loaded: list[InstrumentId] = []

    def on_start(self) -> None:
        self.request_instrument(_LEG)

    def on_instrument(self, instrument: Instrument) -> None:
        self.loaded.append(instrument.id)


@pytest.mark.asyncio
async def test_live_node_request_instrument_round_trips_on_the_ib_data_client() -> None:
    connection = IBConnectionSettings.from_env()
    node = TradingNode(config=build_live_node_config(trader_id=connection.trader_id))
    attach_live_clients(node, connection, instrument_ids=())
    node.build()
    probe = _InstrumentLoadProbe(_ProbeConfig())
    node.trader.add_strategy(probe)

    task = asyncio.create_task(node.run_async())
    try:
        # the live IB data client qualifies the leg on demand and delivers it to on_instrument
        await eventually(lambda: _LEG in probe.loaded, timeout=60.0)
        assert _LEG in probe.loaded
    finally:
        await node.stop_async()
        with suppress(Exception):  # best-effort drain of the node run task
            await asyncio.wait_for(task, timeout=30.0)
        node.dispose()
