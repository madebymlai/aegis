"""One Catalog-registered historical request-engine lifecycle."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import MessageBus, TestClock
from nautilus_trader.config import DataEngineConfig
from nautilus_trader.data.client import DataClient
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.model.identifiers import TraderId

from aegis_data.storage import Catalog

_TRADER_ID = TraderId("AEGIS-RESEARCH-001")


@dataclass(frozen=True)
class CatalogClientFailure:
    """A client fault that the message bus could not propagate to its caller."""

    cause: Exception


@dataclass
class CatalogClientFailureRecorder:
    """Client-owned typed failure state for one synchronous request."""

    failure: CatalogClientFailure | None = None

    def record(self, cause: Exception) -> None:
        self.failure = CatalogClientFailure(cause)


@dataclass(frozen=True)
class CatalogClientBinding:
    """A data client and the typed failure query for its current request."""

    client: DataClient
    failure: Callable[[], CatalogClientFailure | None]


type CatalogClientBindingFactory = Callable[
    [MessageBus, Cache, TestClock],
    CatalogClientBinding,
]
type CatalogRequestFactory = Callable[
    [TestClock, Callable[[object], None]],
    Any,
]


@dataclass(frozen=True)
class CatalogRequestOutcome:
    """Completed responses and client fault from one engine request."""

    responses: tuple[object, ...]
    failure: CatalogClientFailure | None


def run_catalog_request(
    catalog: Catalog,
    *,
    end_ns: int,
    client_factory: CatalogClientBindingFactory | None,
    request_factory: CatalogRequestFactory,
) -> CatalogRequestOutcome:
    """Run one request while hiding all Catalog DataEngine infrastructure."""
    clock = TestClock()
    clock.set_time(end_ns + 1)
    msgbus = MessageBus(trader_id=_TRADER_ID, clock=clock)
    cache = Cache()
    engine = DataEngine(msgbus, cache, clock, DataEngineConfig())
    catalog.register_with(engine)
    binding = None if client_factory is None else client_factory(msgbus, cache, clock)
    if binding is not None:
        engine.register_default_client(binding.client)
    engine.start()
    completed: list[object] = []
    request = request_factory(clock, completed.append)
    try:
        msgbus.request(endpoint="DataEngine.request", request=request)
    finally:
        engine.stop()
    return CatalogRequestOutcome(
        responses=tuple(completed),
        failure=None if binding is None else binding.failure(),
    )
