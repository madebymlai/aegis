"""Research Bar warming delegated to Nautilus's data engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.client import MarketDataClient
from nautilus_trader.data.messages import RequestBars
from nautilus_trader.model.data import BarType

from aegis_data._catalog_request import (
    CatalogClientBinding,
    run_catalog_request,
)
from aegis_data.storage import Catalog, CatalogInterval


type ResearchBarClientFactory = Callable[
    [MessageBus, Cache, TestClock],
    MarketDataClient,
]


class CatalogBarRequestCompletionError(RuntimeError):
    """Nautilus did not complete a synchronous research Bar request."""


@dataclass(frozen=True)
class CatalogBarWarmer:
    """Warm Catalog Bars through Nautilus's request, gap, and write-back path."""

    catalog: Catalog
    client_factory: ResearchBarClientFactory

    def warm_bars(self, bar_type: BarType, interval: CatalogInterval) -> bool:
        """Request one full window; Nautilus dispatches only its missing intervals."""
        outcome = run_catalog_request(
            self.catalog,
            end_ns=interval.end_ns,
            client_factory=lambda msgbus, cache, clock: CatalogClientBinding(
                self.client_factory(msgbus, cache, clock),
                lambda: None,
            ),
            request_factory=lambda clock, callback: RequestBars(
                bar_type=bar_type,
                start=interval.start.to_pydatetime(),
                end=interval.end.to_pydatetime(),
                limit=0,
                client_id=None,
                venue=bar_type.instrument_id.venue,
                callback=callback,
                request_id=UUID4(),
                ts_init=clock.timestamp_ns(),
                params={"update_catalog": True},
            ),
        )
        if not outcome.responses:
            raise CatalogBarRequestCompletionError(
                f"Nautilus did not complete Bar request for {bar_type}"
            )
        return getattr(outcome.responses[-1], "client_id", None) is not None


__all__ = [
    "CatalogBarRequestCompletionError",
    "CatalogBarWarmer",
    "ResearchBarClientFactory",
]
