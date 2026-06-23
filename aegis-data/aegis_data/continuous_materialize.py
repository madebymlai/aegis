"""In-process materialisation of a back-adjusted continuous-future series (Path A).

Nautilus's ``DataEngine`` owns the back-adjustment arithmetic; this drives it from a
**bare in-process ``DataEngine``** — no ``BacktestNode`` / ``TradingNode`` — over a
one-shot historical ``request_bars`` carrying the roll-transition table
(:meth:`~aegis_data.continuous_future.ContinuousFuture.request_params`).  The adjusted
series is captured off the historical-bars topic and returned; it is **never
persisted** (r8b.2).  Research reads its continuous series through here; live reads the
same engine arithmetic through ``subscribe_bars`` on the trading node.

Mechanism (``engine.pyx``): a ``RequestBars`` whose ``params`` carry
``continuous_future_transitions`` is routed to ``_handle_continuous_future_request``,
which walks the chain segment by segment, fires a child leg ``RequestBars`` per
segment, and feeds each leg's raw bars into an internal aggregator with
``BarBuilder.set_adjustment(offset, mode)``.  The leg instruments must be cached
``FuturesContract``\\ s (else the engine warns and returns without emitting).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.common.data_topics import TopicCache
from nautilus_trader.config import DataEngineConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.client import MarketDataClient
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.data.messages import RequestBars
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import ClientId, InstrumentId, TraderId
from nautilus_trader.model.instruments import Instrument

from aegis_data.continuous_future import ContinuousFuture

_CLIENT_ID = ClientId("AEGIS-CONT")
_TRADER_ID = TraderId("AEGIS-CONT-001")
_SETTLE_BUFFER_NS = 2 * 86_400_000_000_000  # 'now' a touch past the last bar so it resolves


class _LegBarClient(MarketDataClient):
    """Answers each segment's leg ``request_bars`` from a pre-fetched leg-bar map — the
    only data source the in-process continuous walk needs."""

    def __init__(self, client_id, msgbus, cache, clock, venue, leg_bars) -> None:  # noqa: ANN001
        super().__init__(client_id, msgbus, cache, clock, venue, None)
        self._leg_bars = leg_bars

    def _connect(self) -> None:
        pass

    def _disconnect(self) -> None:
        pass

    def request_bars(self, request) -> None:  # noqa: ANN001
        bars = self._leg_bars.get(request.bar_type.instrument_id, ())
        start = request.start.value if request.start is not None else None
        end = request.end.value if request.end is not None else None
        selected = [
            bar
            for bar in bars
            if (start is None or bar.ts_event >= start) and (end is None or bar.ts_event <= end)
        ]
        self._handle_bars_py(
            request.bar_type, selected, request.id, request.start, request.end, request.params
        )


def materialize_continuous_bars(
    future: ContinuousFuture,
    *,
    leg_instruments: Sequence[Instrument],
    leg_bars: Mapping[InstrumentId, Sequence[Bar]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[Bar]:
    """Materialise ``future``'s adjusted continuous bars over ``[start, end]``.

    ``leg_bars`` supplies each leg's raw ``EXTERNAL`` bars (keyed by the leg's native
    ``InstrumentId``); ``leg_instruments`` are the matching cached ``FuturesContract``
    definitions.  Returns the adjusted continuous bars in event-time order — the engine
    stamps each at its bucket close and omits the final still-forming bucket.
    """
    clock = TestClock()
    clock.set_time(int(end.value) + _SETTLE_BUFFER_NS)
    msgbus = MessageBus(trader_id=_TRADER_ID, clock=clock)
    cache = Cache()
    for instrument in leg_instruments:
        cache.add_instrument(instrument)

    venue = future.target_bar_type.instrument_id.venue
    engine = DataEngine(msgbus, cache, clock, DataEngineConfig())
    engine.register_default_client(
        _LegBarClient(_CLIENT_ID, msgbus, cache, clock, venue, leg_bars)
    )
    engine.start()

    collected: list[Bar] = []
    msgbus.subscribe(
        topic=TopicCache().get_bars_topic(future.target_bar_type.standard(), historical=True),
        handler=collected.append,
    )
    msgbus.request(
        endpoint="DataEngine.request",
        request=RequestBars(
            bar_type=future.target_bar_type,
            start=start.to_pydatetime(),
            end=end.to_pydatetime(),
            limit=0,
            client_id=None,
            venue=venue,
            callback=lambda _response: None,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params=future.request_params(),
        ),
    )
    engine.stop()
    collected.sort(key=lambda bar: bar.ts_event)
    return collected


__all__ = ["materialize_continuous_bars"]
