"""Trader-owned Nautilus wiring for streaming Custom Data."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import msgspec
import pandas as pd
from nautilus_trader.common.actor import Actor
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model import DataType
from nautilus_trader.model.identifiers import ClientId

from aegis_data.custom_data import (
    CustomDataAdapterMap,
    CustomDataProviderPort,
    InvalidLiveCustomDataCapabilityError,
    LiveCustomDataCapability,
    capture,
)
from aegis_data import custom_kinds
from aegis_data.custom_kinds import CustomDataRegistry
from aegis_data.storage import Catalog

from aegis_trader.bundles.book import AssembledBook
from aegis_trader.trader.book_startup import startup_history_start
from aegis_trader.trader.sleeve_arrays import ArrayNeed, SleeveArrays


class LiveDataClientConflictError(ValueError):
    """Raised when two live-data capabilities claim the same client ID."""

    def __init__(self, client_id: ClientId) -> None:
        super().__init__(f"live data client ID is already configured: {client_id}")
        self.client_id = client_id


class _CustomDataCaptureActor(Actor):
    """Subscribe to native custom-data streams and write every event to the catalog."""

    def __init__(
        self,
        subscriptions: tuple[tuple[ClientId, type[Data]], ...],
        catalog: Catalog,
        registry: CustomDataRegistry | None,
    ) -> None:
        super().__init__()
        self._subscriptions = subscriptions
        self._record_types = frozenset(record_type for _, record_type in subscriptions)
        self._catalog = catalog
        self._registry = registry

    def on_start(self) -> None:
        for client_id, record_type in self._subscriptions:
            self.subscribe_data(
                DataType(record_type),
                client_id=client_id,
            )

    def on_data(self, data: Data) -> None:
        if type(data) in self._record_types:
            capture(data, catalog=self._catalog, registry=self._registry)

    def on_stop(self) -> None:
        for client_id, record_type in self._subscriptions:
            self.unsubscribe_data(
                DataType(record_type),
                client_id=client_id,
            )


def build_live_sleeve_arrays(
    adapters: CustomDataAdapterMap,
    *,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> SleeveArrays:
    """Build the complete live Sleeve array module."""
    return SleeveArrays.live(
        catalog=catalog,
        providers=_historical_providers_by_record_type(adapters),
        registry=registry,
    )


def warm_live_custom_data(
    book: AssembledBook,
    arrays: SleeveArrays,
    *,
    now: datetime,
) -> None:
    """Fill each live sleeve's declared Custom Data startup window."""
    for bundle in book.sleeves.values():
        start = startup_history_start(
            now,
            timeframe=bundle.contract.timeframe,
            required_bar_window=bundle.contract.lookback_bars + 1,
        )
        arrays.ensure(
            ArrayNeed.from_contract(
                bundle.contract,
                start=pd.Timestamp(start),
                end=pd.Timestamp(now),
            )
        )


def add_live_custom_data(
    node: TradingNode,
    adapters: CustomDataAdapterMap,
    *,
    catalog: Catalog,
    registry: CustomDataRegistry | None = None,
) -> None:
    """Register every stream-capable provider without disturbing existing clients."""
    entries = _live_entries(adapters, registry)
    capabilities: list[LiveCustomDataCapability] = []
    for _record_type, capability in entries:
        if capability not in capabilities:
            capabilities.append(capability)
    configured_client_names = set(node._config.data_clients)
    for capability in capabilities:
        client_name = capability.client_name.value
        if client_name in configured_client_names:
            raise LiveDataClientConflictError(ClientId(client_name))
        configured_client_names.add(client_name)

    if not capabilities:
        return

    node._config = msgspec.structs.replace(
        node._config,
        data_clients={
            **node._config.data_clients,
            **{
                capability.client_name.value: capability.config
                for capability in capabilities
            },
        },
    )
    subscriptions: list[tuple[ClientId, type[Data]]] = []
    for capability in capabilities:
        client_id = ClientId(capability.client_name.value)
        node.add_data_client_factory(capability.client_name.value, capability.factory)
        subscriptions.extend(
            (client_id, record_type)
            for record_type, candidate in entries
            if candidate == capability
        )
    if subscriptions:
        node.trader.add_actor(
            _CustomDataCaptureActor(
                tuple(dict.fromkeys(subscriptions)),
                catalog,
                registry,
            )
        )


def _live_entries(
    adapters: CustomDataAdapterMap,
    registry: CustomDataRegistry | None,
) -> tuple[tuple[type[Data], LiveCustomDataCapability], ...]:
    kinds = registry if registry is not None else custom_kinds.declared_custom_data_kinds()
    entries: list[tuple[type[Data], LiveCustomDataCapability]] = []
    for record_type, provider in adapters.items():
        kind = kinds.kind_for(record_type)
        if kind.live is None:
            continue
        describe_capability = getattr(provider, "live_data_capability", None)
        if describe_capability is None:
            continue
        capability = describe_capability()
        if not isinstance(capability, LiveCustomDataCapability):
            raise InvalidLiveCustomDataCapabilityError(
                "live_data_capability() must return LiveCustomDataCapability"
            )
        entries.append((record_type, capability))
    return tuple(entries)


def _historical_providers_by_record_type(
    adapters: CustomDataAdapterMap,
) -> dict[type[Data], CustomDataProviderPort[Any]]:
    return {
        record_type: cast(CustomDataProviderPort[Any], adapter)
        for record_type, adapter in adapters.items()
        if getattr(adapter, "request_records", None) is not None
    }


__all__ = [
    "LiveDataClientConflictError",
    "add_live_custom_data",
    "build_live_sleeve_arrays",
    "warm_live_custom_data",
]
