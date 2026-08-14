"""Research Bar warming delegated to Nautilus's data engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import DataEngineConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.client import MarketDataClient
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.data.messages import RequestBars
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import TraderId

from aegis_data.storage import Catalog, CatalogInterval


_TRADER_ID = TraderId("AEGIS-RESEARCH-001")


type ResearchBarClientFactory = Callable[
    [MessageBus, Cache, TestClock],
    MarketDataClient,
]


class NautilusBarRequestCompletionError(RuntimeError):
    """Nautilus did not complete a synchronous research Bar request."""


@dataclass(frozen=True)
class NautilusBarWarmer:
    """Warm Catalog Bars through Nautilus's request, gap, and write-back path."""

    catalog: Catalog
    client_factory: ResearchBarClientFactory

    def warm_bars(self, bar_type: BarType, interval: CatalogInterval) -> bool:
        """Request one full window; Nautilus dispatches only its missing intervals."""
        clock = TestClock()
        clock.set_time(interval.end_ns + 1)
        msgbus = MessageBus(trader_id=_TRADER_ID, clock=clock)
        cache = Cache()
        engine = DataEngine(msgbus, cache, clock, DataEngineConfig())
        self.catalog.register_with(engine)
        engine.register_default_client(self.client_factory(msgbus, cache, clock))
        engine.start()
        completed: list[object] = []
        request = RequestBars(
            bar_type=bar_type,
            start=interval.start.to_pydatetime(),
            end=interval.end.to_pydatetime(),
            limit=0,
            client_id=None,
            venue=bar_type.instrument_id.venue,
            callback=completed.append,
            request_id=UUID4(),
            ts_init=clock.timestamp_ns(),
            params={"update_catalog": True},
        )
        try:
            msgbus.request(endpoint="DataEngine.request", request=request)
        finally:
            engine.stop()
        if not completed:
            raise NautilusBarRequestCompletionError(
                f"Nautilus did not complete Bar request for {bar_type}"
            )
        return getattr(completed[-1], "client_id", None) is not None


__all__ = [
    "NautilusBarRequestCompletionError",
    "NautilusBarWarmer",
    "ResearchBarClientFactory",
]
