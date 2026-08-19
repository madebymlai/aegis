"""AC3 forced-roll golden on a REAL Nautilus live data engine (r8b.9 .5, Model 2).

Deterministic and CI-runnable — no IB, no network: the real ``RebalanceStrategy`` registered on a
real ``LiveDataEngine`` (asyncio loop, message bus, cache, portfolio) with a recording
``MockMarketDataClient``.  It drives the roll choreography and asserts it traverses the live engine
end-to-end — the live-async path the unit harnesses can only exercise in isolation:

    roll detected → request_instrument(new front) → on_instrument → subscribe(new) +
    unsubscribe(old) + SleeveLedger rebased by the roll Δ

The new front is loaded into the cache by the engine's reply to ``request_instrument`` (Slice G:
no preloaded leg horizon), then subscribed in ``on_instrument`` — proving subscribe/order methods
see the instrument the dynamic load brought in.

Scope: the strategy's full ``on_start``/``on_stop`` lifecycle (warmup, gates, NautilusMarketData,
pipeline) needs the whole node environment and is covered elsewhere; here they are no-ops so the
test isolates the roll seam on the real engine. The data-layer model owns real roll detection; this
fixture's desk simply advances its front on the next bar so the strategy's roll handler fires.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.live.data_engine import LiveDataEngine
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.test_kit.functions import eventually
from nautilus_trader.test_kit.mocks.data import MockMarketDataClient
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from aegis_runtime.domain.rebasing import Rebasing, spread_rebasing
from aegis_data.bar_type import raw_bar_type
from aegis_data.storage import Catalog
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import (
    RequestInstrument,
    RollEvent,
    RollIntentBatch,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.trader.pipeline import RebalancePipeline
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_CONT = InstrumentId.from_str("ES.XCME")
_OLD = InstrumentId.from_str("ESM4.XCME")
_NEW = InstrumentId.from_str("ESU4.XCME")
_SPREAD = 5.0


class _RecordingClient(MockMarketDataClient):
    """Records the subscribe / unsubscribe / request_instrument commands the engine routes here,
    and answers request_instrument with the leg set on ``instrument`` (→ on_instrument)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.subscribed: list[object] = []
        self.unsubscribed: list[object] = []
        self.requested: list[InstrumentId] = []

    def subscribe_bars(self, command: object) -> None:
        self.subscribed.append(command.bar_type)  # type: ignore[attr-defined]
        super().subscribe_bars(command)  # type: ignore[arg-type]

    def unsubscribe_bars(self, command: object) -> None:
        self.unsubscribed.append(command.bar_type)  # type: ignore[attr-defined]

    def request_instrument(self, request: object) -> None:
        self.requested.append(request.instrument_id)  # type: ignore[attr-defined]
        super().request_instrument(request)  # type: ignore[arg-type]


class _RecordingLedger:
    def __init__(self) -> None:
        self.rebased: list[dict[InstrumentId, Rebasing]] = []

    def rebase_closes(self, rebasings: dict[InstrumentId, Rebasing]) -> None:
        self.rebased.append(dict(rebasings))


class _RecordingPipeline:
    apply_roll = RebalancePipeline.apply_roll

    def __init__(self, ledger: _RecordingLedger) -> None:
        self._ledger = ledger


class _RollingDesk:
    """A Roll Desk stand-in that emits the forced-roll intent batch."""

    def __init__(self, continuous_id: InstrumentId, front: InstrumentId, roll_to: InstrumentId) -> None:
        self._continuous_id = continuous_id
        self._front = front
        self._roll_to = roll_to
        self._pending: set[InstrumentId] = set()

    def start(self, **_kwargs: object) -> tuple[SubscribeBars]:
        return (SubscribeBars(self._front, "1D"),)

    def continuous_id(self, leg: object) -> object | None:
        return self._continuous_id if leg == self._front else None

    def on_bar(self, bar: object) -> RollIntentBatch:
        if bar.bar_type.instrument_id != self._front:  # type: ignore[attr-defined]
            return ()
        old_front = self._front
        self._front = self._roll_to
        self._pending.add(self._front)
        return (
            UnsubscribeBars(old_front, "1D"),
            RequestInstrument(self._front),
            RollEvent(self._continuous_id, spread_rebasing(_SPREAD)),
        )

    def on_instrument(self, instrument_id: InstrumentId) -> RollIntentBatch:
        if instrument_id not in self._pending:
            return ()
        self._pending.discard(instrument_id)
        return (SubscribeBars(instrument_id, "1D"),)

    def front_leg(self, instrument_id: InstrumentId) -> InstrumentId | None:
        if instrument_id != self._continuous_id:
            return None
        return self._front


class _RollHarnessStrategy(RebalanceStrategy):
    """Isolates the roll seam: the full-lifecycle hooks (covered elsewhere) are no-ops, so the test
    drives the roll directly on the real engine."""

    def on_start(self) -> None:  # noqa: D401 - skip full startup
        pass

    def on_stop(self) -> None:  # noqa: D401 - skip full teardown
        pass


def _leg(symbol: str) -> FuturesContract:
    return TestInstrumentProvider.future(symbol=symbol, venue="XCME")


def _front_leg_bar(instrument_id: InstrumentId) -> object:
    return SimpleNamespace(bar_type=SimpleNamespace(instrument_id=instrument_id))


@pytest.mark.asyncio
async def test_forced_roll_drives_request_instrument_on_instrument_subscribe_on_the_live_engine(
    tmp_path: Path,
) -> None:
    clock = LiveClock()
    trader_id = TraderId("ROLL-TESTER-001")
    msgbus = MessageBus(trader_id=trader_id, clock=clock)
    cache = Cache()
    engine = LiveDataEngine(loop=asyncio.get_running_loop(), msgbus=msgbus, cache=cache, clock=clock)

    client = _RecordingClient(ClientId("XCME"), msgbus, cache, clock)
    client.instrument = _leg("ESU4")  # what the engine returns for request_instrument(_NEW)
    engine.register_client(client)
    cache.add_instrument(_leg("ESM4"))  # the current front is already known at startup

    book = BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"), wheel_filename="t.whl", risk_share=1.0),),
        base_currency="USD",
    )
    strategy = _RollHarnessStrategy(
        RebalanceStrategyConfig(book=book, warmup_cache_on_start=False),
        arrays=SleeveArrays.bar_only(),
        catalog=Catalog.open(tmp_path / "catalog"),
    )
    portfolio = Portfolio(msgbus, cache, clock)
    strategy.register(trader_id, portfolio, msgbus, cache, clock)
    ledger = _RecordingLedger()
    pipeline = _RecordingPipeline(ledger)
    strategy._pipeline = pipeline  # type: ignore[assignment]
    desk = _RollingDesk(_CONT, _OLD, _NEW)
    strategy._roll_desk = desk  # type: ignore[assignment]

    engine.start()
    strategy.start()
    try:
        await eventually(lambda: engine.is_running)
        # live startup state: the current front leg is already subscribed (it is in the cache)
        strategy._apply_roll_intents(desk.start())
        await eventually(lambda: raw_bar_type(_OLD, "1D") in client.subscribed)

        # a front-leg bar advances the desk's causal front → the relay applies the roll batch
        strategy._apply_roll_intents(desk.on_bar(_front_leg_bar(_OLD)))

        # the new front is loaded on demand then subscribed in on_instrument — the live-async seam
        await eventually(lambda: raw_bar_type(_NEW, "1D") in client.subscribed, timeout=5.0)

        assert client.requested == [_NEW]  # dynamic load issued for the uncached new front
        assert cache.instrument(_NEW) is not None  # engine's reply loaded it into the cache
        assert client.unsubscribed == [raw_bar_type(_OLD, "1D")]  # old front execution sub dropped
        assert ledger.rebased == [{_CONT: spread_rebasing(_SPREAD)}]  # ledger carried into new basis
        assert desk.front_leg(_CONT) == _NEW  # routing now follows the new front
    finally:
        strategy.stop()
        engine.stop()
        await eventually(lambda: not engine.is_running)
        engine.dispose()
