"""Live Custom Data wiring through Nautilus's node and Actor seams."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import LiveDataClientConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.core.data import Data
from nautilus_trader.data.messages import RequestData, SubscribeData, UnsubscribeData
from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model import CustomData, DataType
from nautilus_trader.model.identifiers import ClientId, InstrumentId

from aegis_data.custom_data import (
    FixtureRecord,
    InvalidLiveCustomDataCapabilityError,
    LiveCustomDataCapability,
    LiveDataClientName,
    arrays,
)
from aegis_trader.trader.live_custom_data import (
    LiveDataClientConflictError,
    add_live_custom_data,
)


class _FixtureClient(LiveDataClient):
    async def _connect(self) -> None:
        pass

    async def _disconnect(self) -> None:
        pass

    async def _subscribe(self, command: SubscribeData) -> None:
        pass

    async def _unsubscribe(self, command: UnsubscribeData) -> None:
        pass

    async def _request(self, request: RequestData) -> None:
        pass


class _FixtureFactory(LiveDataClientFactory):
    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: LiveDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> LiveDataClient:
        return _FixtureClient(
            loop=loop,
            client_id=ClientId(name),
            venue=None,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )


class _StreamingProvider:
    def __init__(self, config: LiveDataClientConfig) -> None:
        self._config = config

    def live_data_capability(self) -> LiveCustomDataCapability:
        return LiveCustomDataCapability(
            client_name=LiveDataClientName("FIXTURE"),
            config=self._config,
            factory=_FixtureFactory,
            record_types=(FixtureRecord,),
        )


class _FetchOnlyProvider:
    pass


class _InvalidStreamingProvider:
    def live_data_capability(self) -> object:
        return object()


class _Trader:
    def __init__(self) -> None:
        self.actors: list[object] = []

    def add_actor(self, actor: object) -> None:
        self.actors.append(actor)


class _Node:
    def __init__(
        self,
        broker_config: LiveDataClientConfig,
        broker_client_id: str = "INTERACTIVE_BROKERS",
    ) -> None:
        self._config = TradingNodeConfig(data_clients={broker_client_id: broker_config})
        self.data_factories: dict[str, object] = {}
        self.trader = _Trader()

    def add_data_client_factory(self, name: str, factory: object) -> None:
        self.data_factories[name] = factory


@contextmanager
def _native_capture(
    catalog_path: Path,
) -> Iterator[Callable[[Data], None]]:
    loop = asyncio.new_event_loop()
    node = TradingNode(
        TradingNodeConfig(logging=LoggingConfig(log_level="ERROR")),
        loop=loop,
    )
    add_live_custom_data(
        node,
        (_StreamingProvider(LiveDataClientConfig()),),
        catalog_path=catalog_path,
    )
    node.build()
    actor = node.trader.actors()[0]
    data_engine = node.kernel.data_engine
    data_engine.start()
    node.trader.start_actor(actor.id)

    def deliver(record: Data) -> None:
        data_engine.process(CustomData(DataType(type(record)), record))
        loop.run_until_complete(asyncio.sleep(0))

    try:
        yield deliver
    finally:
        node.trader.stop_actor(actor.id)
        loop.run_until_complete(asyncio.sleep(0))
        data_engine.stop()
        loop.run_until_complete(
            asyncio.gather(
                data_engine.get_cmd_queue_task(),
                data_engine.get_req_queue_task(),
                data_engine.get_res_queue_task(),
                data_engine.get_data_queue_task(),
            )
        )
        node.dispose()


def test_live_custom_data_merges_client_config_and_registers_its_factory(
    tmp_path: Path,
) -> None:
    broker_config = LiveDataClientConfig()
    fixture_config = LiveDataClientConfig()
    node = _Node(broker_config)

    add_live_custom_data(
        node,
        (_FetchOnlyProvider(), _StreamingProvider(fixture_config)),
        catalog_path=tmp_path,
    )

    assert node._config.data_clients == {
        "INTERACTIVE_BROKERS": broker_config,
        "FIXTURE": fixture_config,
    }
    assert node.data_factories == {"FIXTURE": _FixtureFactory}


def test_live_custom_data_rejects_a_client_id_already_owned_by_the_node(
    tmp_path: Path,
) -> None:
    broker_config = LiveDataClientConfig()
    node = _Node(broker_config, broker_client_id="FIXTURE")

    with pytest.raises(LiveDataClientConflictError, match="FIXTURE"):
        add_live_custom_data(
            node,
            (_StreamingProvider(LiveDataClientConfig()),),
            catalog_path=tmp_path,
        )

    assert node._config.data_clients == {"FIXTURE": broker_config}
    assert node.data_factories == {}


def test_live_custom_data_rejects_an_invalid_provider_capability(tmp_path: Path) -> None:
    node = _Node(LiveDataClientConfig())

    with pytest.raises(InvalidLiveCustomDataCapabilityError):
        add_live_custom_data(
            node,
            (_InvalidStreamingProvider(),),
            catalog_path=tmp_path,
        )

    assert node.data_factories == {}


def test_native_custom_data_delivery_is_captured_for_arrays(tmp_path: Path) -> None:
    timestamp = pd.Timestamp("2024-01-02", tz="UTC")
    instrument_id = InstrumentId.from_str("SPY.ARCA")
    record = FixtureRecord(
        timestamp.value,
        timestamp.value,
        instrument_id=instrument_id,
        value=7.0,
        provider="fixture-live",
    )
    with _native_capture(tmp_path) as deliver:
        deliver(record)
        panels = arrays(
            ("FixtureValue", "FixtureAvailable"),
            (instrument_id,),
            index=pd.DatetimeIndex([timestamp]),
            catalog_path=tmp_path,
        )

        assert panels["FixtureValue"].to_numpy().tolist() == [[7.0]]
        assert panels["FixtureAvailable"].to_numpy().tolist() == [[1.0]]
