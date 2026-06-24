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
test isolates the roll seam on the real engine.  The feed's own causal-roll detection is unit-tested
in ``test_continuous_feed.py``; this fixture's feed simply advances its front on the next bar so the
strategy's roll handler fires.
"""

from __future__ import annotations

import asyncio
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

from aegis_data.rebasing import Rebasing, spread_rebasing
from aegis_trader.data import raw_bar_type
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
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


class _RollingFeed:
    """A feed that advances its causal front to ``roll_to`` on the next bar (real causal detection is
    unit-tested separately); exposes the front + the uniform roll Δ the strategy re-bases by."""

    def __init__(self, continuous_id: InstrumentId, front: InstrumentId, roll_to: InstrumentId) -> None:
        self.continuous_id = continuous_id
        self._front = front
        self._roll_to = roll_to

    def front_contract(self) -> InstrumentId:
        return self._front

    def on_bar(self, _bar: object) -> None:
        self._front = self._roll_to

    def last_rebasing(self) -> Rebasing:
        return spread_rebasing(_SPREAD)


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
async def test_forced_roll_drives_request_instrument_on_instrument_subscribe_on_the_live_engine() -> None:
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
    strategy = _RollHarnessStrategy(RebalanceStrategyConfig(book=book, warmup_cache_on_start=False))
    portfolio = Portfolio(msgbus, cache, clock)
    strategy.register(trader_id, portfolio, msgbus, cache, clock)
    strategy._book_timeframe = "1D"
    ledger = _RecordingLedger()
    strategy._sleeve_ledger = ledger  # type: ignore[assignment]
    strategy._install_feeds([_RollingFeed(_CONT, _OLD, _NEW)])  # type: ignore[list-item]

    engine.start()
    strategy.start()
    try:
        await eventually(lambda: engine.is_running)
        # live startup state: the current front leg is already subscribed (it is in the cache)
        strategy._ensure_leg_subscribed(_OLD)
        await eventually(lambda: raw_bar_type(_OLD, "1D") in client.subscribed)

        # a front-leg bar advances the feed's causal front → the strategy's roll handler fires
        strategy._drive_feed(_front_leg_bar(_OLD))

        # the new front is loaded on demand then subscribed in on_instrument — the live-async seam
        await eventually(lambda: raw_bar_type(_NEW, "1D") in client.subscribed, timeout=5.0)

        assert client.requested == [_NEW]  # dynamic load issued for the uncached new front
        assert cache.instrument(_NEW) is not None  # engine's reply loaded it into the cache
        assert client.unsubscribed == [raw_bar_type(_OLD, "1D")]  # old front execution sub dropped
        assert ledger.rebased == [{_CONT: spread_rebasing(_SPREAD)}]  # ledger carried into new basis
        assert set(strategy._leg_to_feed) == {_NEW}  # routing now follows the new front
    finally:
        strategy.stop()
        engine.stop()
        await eventually(lambda: not engine.is_running)
        engine.dispose()
