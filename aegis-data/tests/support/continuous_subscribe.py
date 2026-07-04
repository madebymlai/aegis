"""Live-subscription continuous-future materialiser (the AC4 live-half test oracle).

Drives Nautilus's continuous-future ``subscribe_bars`` roll state machine on a bare
in-process ``DataEngine`` + ``TestClock`` and captures the adjusted *live* series, so
the golden test can pin it byte-for-byte against the request path
(:mod:`aegis_data.continuous_materialize`) and the Decimal oracle — proving live ≡
research.

This is the **subscribe**-path counterpart to the production request-path materialiser.
Production live trading subscribes through the trading node's own ``DataEngine`` (the
strategy calls ``subscribe_bars``), so there is no standalone subscribe materialiser to
ship; this harness exists only to prove the subscribe path emits the *same* adjusted
bars as the request path.

Mechanism (``engine.pyx :: _handle_subscribe_continuous_future_bars`` +
``_handle_continuous_future_subscription_transition``): the continuous ``SubscribeBars``
activates segment 0 (resolves the source leg, applies its offset, subscribes) and arms a
single time alert at the next ``transition_time_ns``; at the alert the engine deactivates
the current leg (unsubscribe source), activates the next (re-apply offset, subscribe
source), and re-arms.  The harness walks the business-day timeline on a ``TestClock``:
advancing to each leg bar's event time fires the roll alerts and internal bucket closes
due in between (exactly what a ``LiveClock`` thread dispatches in production), then it
publishes that day's leg bars on their live source topics — only the active leg is
subscribed, so the state machine alone decides the active source.

``time_bars_build_with_no_updates=False`` matches what the live node sets (r8b.2 AC6)
and what the request path forces internally: it is the precondition for byte-exactness
(the subscription path otherwise emits non-trading-day flat bars — prototype NOTES.md
V5 CONFIG finding).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.common.data_topics import TopicCache
from nautilus_trader.config import DataEngineConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.client import MarketDataClient
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.data.messages import SubscribeBars
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId
from nautilus_trader.model.instruments import Instrument

from aegis_data.continuous_future import ContinuousFuture

_CLIENT_ID = ClientId("AEGIS-CONT-SUB")
_TRADER_ID = TraderId("AEGIS-CONT-SUB-001")


@dataclass(frozen=True)
class SubscriptionRun:
    """The outcome of a live continuous-subscription walk: the adjusted live bars in
    event-time order, plus the ordered per-segment subscribe/unsubscribe choreography
    the engine issued (the AC3 roll evidence — ``(action, source-leg id)``)."""

    bars: list[Bar]
    roll_events: tuple[tuple[str, InstrumentId], ...]


class _SubscribeLegClient(MarketDataClient):
    """Records the engine's per-segment subscribe/unsubscribe of source legs — the
    surface a real adapter (the stock IBKR client) exposes to the continuous state
    machine.  It does not stream bars; the harness publishes leg bars directly on each
    leg's live topic, so this client only accepts the engine's child commands."""

    def __init__(self, client_id, msgbus, cache, clock, venue) -> None:  # noqa: ANN001
        super().__init__(client_id, msgbus, cache, clock, venue, None)
        self.roll_events: list[tuple[str, InstrumentId]] = []

    def _connect(self) -> None:
        pass

    def _disconnect(self) -> None:
        pass

    def subscribe_bars(self, command) -> None:  # noqa: ANN001
        self._add_subscription_bars(command.bar_type)
        self.roll_events.append(("subscribe", command.bar_type.instrument_id))

    def unsubscribe_bars(self, command) -> None:  # noqa: ANN001
        self._remove_subscription_bars(command.bar_type)
        self.roll_events.append(("unsubscribe", command.bar_type.instrument_id))


def materialize_continuous_bars_via_subscription(
    future: ContinuousFuture,
    *,
    leg_instruments: Sequence[Instrument],
    leg_bars: Mapping[InstrumentId, Sequence[Bar]],
    start: pd.Timestamp,
) -> SubscriptionRun:
    """Materialise ``future``'s adjusted continuous series via a live ``subscribe_bars``.

    ``leg_bars`` supplies each leg's raw ``EXTERNAL`` bars (each carrying its own source
    ``BarType``); ``leg_instruments`` are the matching cached ``FuturesContract``
    definitions; ``start`` seeds the clock before the first bar.  Returns the adjusted
    live bars in event-time order — the engine stamps each at its bucket close and, with
    the timeline flushed one bucket past the last bar, emits the final bucket too (one
    bar more than the bounded request path).
    """
    clock = TestClock()
    clock.set_time(int(start.value))  # 'now' = window open, before any bar
    msgbus = MessageBus(trader_id=_TRADER_ID, clock=clock)
    cache = Cache()
    for instrument in leg_instruments:
        cache.add_instrument(instrument)

    venue = future.target_bar_type.instrument_id.venue
    engine = DataEngine(
        msgbus, cache, clock, DataEngineConfig(time_bars_build_with_no_updates=False)
    )
    client = _SubscribeLegClient(_CLIENT_ID, msgbus, cache, clock, venue)
    engine.register_default_client(client)
    engine.start()

    topics = TopicCache()
    collected: list[Bar] = []
    msgbus.subscribe(
        topic=topics.get_bars_topic(future.target_bar_type.standard(), historical=False),
        handler=collected.append,
    )

    engine.execute(
        SubscribeBars(
            bar_type=future.target_bar_type,
            client_id=None,
            venue=venue,
            command_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params=future.request_params(),
        )
    )

    by_ts: dict[int, list[Bar]] = defaultdict(list)
    for bars in leg_bars.values():
        for bar in bars:
            by_ts[bar.ts_event].append(bar)
    day_ts = sorted(by_ts)
    src_topic: dict[object, str] = {}
    for ts in day_ts:
        for handler in clock.advance_time(ts):
            handler.handle()
        for bar in by_ts[ts]:
            topic = src_topic.setdefault(
                bar.bar_type,
                topics.get_bars_topic(bar.bar_type.standard(), historical=False),
            )
            msgbus.publish(topic=topic, msg=bar)
    # Flush: step one bucket past the last bar so the final daily bucket closes & emits.
    period_ns = int(future.target_bar_type.spec.timedelta.value)
    for handler in clock.advance_time(day_ts[-1] + period_ns):
        handler.handle()

    engine.stop()
    collected.sort(key=lambda bar: bar.ts_event)
    return SubscriptionRun(bars=collected, roll_events=tuple(client.roll_events))


__all__ = ["SubscriptionRun", "materialize_continuous_bars_via_subscription"]
