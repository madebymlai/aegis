"""Live Custom Data wiring through Nautilus's node and Actor seams."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pandas as pd
import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import (
    LiveDataClientConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.core.data import Data
from nautilus_trader.data.messages import RequestData, SubscribeData, UnsubscribeData
from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model import CustomData, DataType
from nautilus_trader.model.identifiers import ClientId, InstrumentId

from aegis_data.custom_data import (
    InvalidLiveCustomDataCapabilityError,
    LiveCustomDataCapability,
    LiveDataClientName,
)
from aegis_data.storage import Catalog
from aegis_trader.data.market_data import MarketBar
from aegis_trader.trader.live_custom_data import (
    LiveDataClientConflictError,
    build_live_sleeve_arrays,
    live_custom_data,
    warm_live_custom_data,
)
from aegis_trader.trader.sleeve_arrays import ArrayNeed, SleeveArrayGrid
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from tests.support.factories import assemble_test_book, make_bundle
from tests.support.custom_data import FixtureRecord


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
    def __init__(
        self,
        config: LiveDataClientConfig,
        available: tuple[FixtureRecord, ...] = (),
    ) -> None:
        self._config = config
        self._available = available
        self.requests: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def live_data_capability(self) -> LiveCustomDataCapability:
        return LiveCustomDataCapability(
            client_name=LiveDataClientName("FIXTURE"),
            config=self._config,
            factory=_FixtureFactory,
        )

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[FixtureRecord, ...]:
        self.requests.append((start, end))
        records = tuple(
            record
            for record in self._available
            if record.instrument_id == instrument_id
            and start.value <= record.ts_event <= end.value
        )
        return records


class _InvalidStreamingProvider:
    def live_data_capability(self) -> object:
        return object()


class _Trader:
    def __init__(self) -> None:
        self.actors: list[object] = []

    def add_actor(self, actor: object) -> None:
        self.actors.append(actor)


class _Node:
    def __init__(self) -> None:
        self.data_factories: dict[str, object] = {}
        self.trader = _Trader()

    def add_data_client_factory(self, name: str, factory: object) -> None:
        self.data_factories[name] = factory


@contextmanager
def _native_capture(
    catalog: Catalog,
    provider: _StreamingProvider | None = None,
) -> Iterator[Callable[[Data], None]]:
    loop = asyncio.new_event_loop()
    streaming = live_custom_data(
        {FixtureRecord: provider or _StreamingProvider(LiveDataClientConfig())}
    )
    node = TradingNode(
        TradingNodeConfig(
            logging=LoggingConfig(log_level="ERROR"),
            data_clients=streaming.data_clients,
        ),
        loop=loop,
    )
    streaming.register(
        cast(TradingNode, node),
        catalog=catalog,
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
    streaming = live_custom_data(
        {FixtureRecord: _StreamingProvider(fixture_config)},
        configured_client_names=("INTERACTIVE_BROKERS",),
    )
    config = TradingNodeConfig(
        data_clients={"INTERACTIVE_BROKERS": broker_config, **streaming.data_clients}
    )
    node = _Node()

    streaming.register(
        cast(TradingNode, node),
        catalog=Catalog.open(tmp_path),
    )

    assert config.data_clients == {
        "INTERACTIVE_BROKERS": broker_config,
        "FIXTURE": fixture_config,
    }
    assert node.data_factories == {"FIXTURE": _FixtureFactory}


def test_live_custom_data_rejects_an_already_configured_client_id() -> None:
    with pytest.raises(LiveDataClientConflictError, match="FIXTURE"):
        live_custom_data(
            {FixtureRecord: _StreamingProvider(LiveDataClientConfig())},
            configured_client_names=("FIXTURE",),
        )


def test_live_custom_data_rejects_an_invalid_provider_capability() -> None:
    with pytest.raises(InvalidLiveCustomDataCapabilityError):
        live_custom_data({FixtureRecord: _InvalidStreamingProvider()})


def test_native_capture_gap_is_healed_by_live_array_coverage(tmp_path: Path) -> None:
    first_timestamp = pd.Timestamp("2024-01-01", tz="UTC")
    last_timestamp = pd.Timestamp("2024-01-03", tz="UTC")
    instrument_id = InstrumentId.from_str("SPY.ARCA")
    first = FixtureRecord(
        first_timestamp.value,
        first_timestamp.value,
        instrument_id=instrument_id,
        value=2.0,
        provider="fixture-live",
    )
    last = FixtureRecord(
        last_timestamp.value,
        last_timestamp.value,
        instrument_id=instrument_id,
        value=8.0,
        provider="fixture-live",
    )
    provider = _StreamingProvider(LiveDataClientConfig())
    catalog = Catalog.open(tmp_path)
    with _native_capture(catalog, provider) as deliver:
        deliver(first)
        deliver(last)
    arrays = build_live_sleeve_arrays(
        {FixtureRecord: provider},
        catalog=catalog,
    )
    index = pd.date_range(first_timestamp, last_timestamp, tz="UTC")

    grid = _custom_array_grid(instrument_id, index)

    arrays.ensure(grid.need)
    panels = arrays.project(grid)

    assert provider.requests == [
        (
            pd.Timestamp("2024-01-01 00:00:00.000000001", tz="UTC"),
            pd.Timestamp("2024-01-02 23:59:59.999999999", tz="UTC"),
        )
    ]
    assert panels["FixtureValue"].to_numpy().tolist() == [[2.0], [2.0], [8.0]]


def test_live_array_coverage_rechecks_a_window_that_has_never_stored_a_record(
    tmp_path: Path,
) -> None:
    instrument_id = InstrumentId.from_str("SPY.ARCA")
    index = pd.date_range("2024-01-01", "2024-01-03", tz="UTC")
    seed = _StreamingProvider(LiveDataClientConfig())
    need = ArrayNeed(
        names=("FixtureValue", "FixtureAvailable"),
        instrument_ids=(instrument_id,),
        start=index[0],
        end=index[-1],
    )
    catalog = Catalog.open(tmp_path)
    build_live_sleeve_arrays({FixtureRecord: seed}, catalog=catalog).ensure(need)
    unused = _StreamingProvider(LiveDataClientConfig())

    build_live_sleeve_arrays({FixtureRecord: unused}, catalog=catalog).ensure(need)

    assert unused.requests == [(index[0], index[-1])]


def test_live_startup_warms_the_declared_custom_array_window(
    tmp_path: Path,
) -> None:
    instrument_id = InstrumentId.from_str("SPY.ARCA")
    book_config = BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("fixture"),
                wheel_filename="fixture.whl",
                risk_share=1.0,
            ),
        )
    )
    book = assemble_test_book(
        book_config,
        {
            "fixture.whl": make_bundle(
                required_arrays=(
                    "Close",
                    "FixtureValue",
                    "FixtureAvailable",
                ),
                native_instrument_ids=(instrument_id,),
                lookback_bars=0,
            )
        },
    )
    record_timestamp = pd.Timestamp("2024-01-02", tz="UTC")
    provider = _StreamingProvider(
        LiveDataClientConfig(),
        (
            FixtureRecord(
                record_timestamp.value,
                record_timestamp.value,
                instrument_id=instrument_id,
                value=7.0,
                provider="fixture-history",
            ),
        ),
    )
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)

    arrays = build_live_sleeve_arrays(
        {FixtureRecord: provider},
        catalog=Catalog.open(tmp_path),
    )
    warm_live_custom_data(
        book,
        arrays,
        now=now,
    )

    assert provider.requests == [
        (pd.Timestamp("2023-12-31", tz="UTC"), pd.Timestamp(now))
    ]


def test_live_custom_array_projection_reads_the_warmed_catalog(
    tmp_path: Path,
) -> None:
    instrument_id = InstrumentId.from_str("SPY.ARCA")
    timestamp = pd.Timestamp("2024-01-02", tz="UTC")
    provider = _StreamingProvider(
        LiveDataClientConfig(),
        (
            FixtureRecord(
                timestamp.value,
                timestamp.value,
                instrument_id=instrument_id,
                value=7.0,
                provider="fixture-history",
            ),
        ),
    )
    index = pd.date_range("2024-01-01", "2024-01-03", tz="UTC")
    arrays = build_live_sleeve_arrays(
        {FixtureRecord: provider},
        catalog=Catalog.open(tmp_path),
    )
    grid = _custom_array_grid(instrument_id, index)

    arrays.ensure(grid.need)
    panels = arrays.project(grid)

    assert panels["FixtureValue"].to_numpy().tolist() == [[0.0], [7.0], [7.0]]


def _custom_array_grid(
    instrument_id: InstrumentId,
    index: pd.DatetimeIndex,
) -> SleeveArrayGrid:
    contract = make_bundle(
        required_arrays=("Close", "FixtureValue", "FixtureAvailable"),
        native_instrument_ids=(instrument_id,),
    ).contract
    bars = {
        instrument_id: tuple(
            MarketBar(timestamp.value, 1.0, 1.0, 1.0, 1.0, 1.0) for timestamp in index
        )
    }
    return SleeveArrayGrid.from_bars(contract, bars)
