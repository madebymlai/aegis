"""Layer 2 — real live TradingNode liveness on the IB paper gateway (r8b.9 .5, env-gated).

Connects the actual broker-neutral live ``TradingNode`` (real IB live data + exec clients) to a
running gateway and asserts the LIVE data client's roll-intent path:
``RequestInstrument → on_instrument → SubscribeBars → UnsubscribeBars``.  This covers the
dynamic-leg-load path (Slice G) on the real adapter, distinct from the historical client exercised
in ``test_ibkr_provider_live`` and complementary to the deterministic live-engine golden in
``test_live_node_roll``.

Gated on ``IB_PORT`` + ``IB_ACCOUNT_ID`` + ``TWS_USERNAME`` + ``TWS_PASSWORD`` (the
test connects to the already-running gateway on ``IB_PORT``),
so it is skipped in CI and runs only against an operator's gateway.  No module-level
``importorskip('ibapi')`` — ibapi is imported lazily inside the smoke helper only
when a test runs, keeping collection ibapi-free (the lazy-import guard).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress

import msgspec
import pytest
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.test_kit.functions import eventually

from aegis_data.ibkr import IB_CLIENT_NAME, mic_instrument_provider_config
from aegis_trader.config.connection import IBConnectionSettings
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import RequestInstrument, SubscribeBars, UnsubscribeBars
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.node import build_live_node_config
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_PORT = os.environ.get("IB_PORT")
_ACCOUNT = os.environ.get("IB_ACCOUNT_ID")
_TWS_USERNAME = os.environ.get("TWS_USERNAME")
_TWS_PASSWORD = os.environ.get("TWS_PASSWORD")
# An active dated ES quarterly leg (a real roll loads exactly this kind of leg at runtime).
_LEG = InstrumentId.from_str("ESU6.XCME")

pytestmark = pytest.mark.skipif(
    not (_PORT and _ACCOUNT and _TWS_USERNAME and _TWS_PASSWORD),
    reason=(
        "set IB_PORT + IB_ACCOUNT_ID + TWS_USERNAME + TWS_PASSWORD to run "
        "against a running IB Gateway"
    ),
)


class _RollIntentProbe(RebalanceStrategy):
    """Routes the Roll Desk's live subscribe/unsubscribe intent shape through IB clients."""

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self.loaded: list[InstrumentId] = []
        self.roll_commands_routed = False

    def on_start(self) -> None:
        self._apply_roll_intents((RequestInstrument(_LEG),))

    def on_instrument(self, instrument: Instrument) -> None:
        if self.roll_commands_routed:
            return
        self.loaded.append(instrument.id)
        if instrument.id != _LEG:
            return
        self._apply_roll_intents(
            (
                SubscribeBars(_LEG, "1D"),
                UnsubscribeBars(_LEG, "1D"),
            )
        )
        self.roll_commands_routed = True


def _attach_running_gateway_clients(
    node: TradingNode,
    connection: IBConnectionSettings,
) -> None:
    from nautilus_trader.adapters.interactive_brokers.config import (
        IBMarketDataTypeEnum,
        InteractiveBrokersDataClientConfig,
        InteractiveBrokersExecClientConfig,
    )
    from nautilus_trader.adapters.interactive_brokers.factories import (
        InteractiveBrokersLiveDataClientFactory,
        InteractiveBrokersLiveExecClientFactory,
    )

    provider = mic_instrument_provider_config(load_ids=())
    data_config = InteractiveBrokersDataClientConfig(
        ibg_client_id=connection.client_id,
        ibg_port=connection.port,
        market_data_type=IBMarketDataTypeEnum.REALTIME,
        use_regular_trading_hours=True,
        instrument_provider=provider,
    )
    exec_config = InteractiveBrokersExecClientConfig(
        ibg_client_id=connection.client_id,
        ibg_port=connection.port,
        account_id=connection.account_id,
        instrument_provider=provider,
    )
    node._config = msgspec.structs.replace(
        node._config,
        data_clients={IB_CLIENT_NAME: data_config},
        exec_clients={IB_CLIENT_NAME: exec_config},
    )
    node.add_data_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveExecClientFactory)


def test_live_node_roll_intents_route_subscribe_unsubscribe_on_the_ib_data_client() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_live_node_roll_intent_smoke())
    finally:
        asyncio.set_event_loop(None)
        if not loop.is_closed():
            loop.close()


async def _run_live_node_roll_intent_smoke() -> None:
    connection = IBConnectionSettings.from_env()
    node = TradingNode(config=build_live_node_config(trader_id=connection.trader_id))
    _attach_running_gateway_clients(node, connection)
    node.build()
    probe = _RollIntentProbe(
        RebalanceStrategyConfig(
            book=BookConfig(
                sleeves=(
                    SleeveConfig(
                        name=SleeveName("trend"),
                        wheel_filename="probe.whl",
                        risk_share=1.0,
                    ),
                ),
                base_currency="USD",
            ),
            warmup_cache_on_start=False,
        )
    )
    node.trader.add_strategy(probe)

    task = asyncio.create_task(node.run_async())
    try:
        await eventually(lambda: probe.roll_commands_routed, timeout=60.0)
        assert probe.loaded == [_LEG]
        assert probe.roll_commands_routed is True
    finally:
        await node.stop_async()
        with suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=30.0)
        node.dispose()
