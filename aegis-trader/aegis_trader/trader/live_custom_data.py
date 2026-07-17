"""Trader-owned Nautilus wiring for streaming Custom Data."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import msgspec
from nautilus_trader.common.actor import Actor
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model import DataType
from nautilus_trader.model.identifiers import ClientId

from aegis_data.custom_data import (
    InvalidLiveCustomDataCapabilityError,
    LiveCustomDataCapability,
    capture,
)


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
        catalog_path: Path,
    ) -> None:
        super().__init__()
        self._subscriptions = subscriptions
        self._record_types = frozenset(record_type for _, record_type in subscriptions)
        self._catalog_path = catalog_path

    def on_start(self) -> None:
        for client_id, record_type in self._subscriptions:
            self.subscribe_data(
                DataType(record_type),
                client_id=client_id,
            )

    def on_data(self, data: Data) -> None:
        if type(data) in self._record_types:
            capture(data, catalog_path=self._catalog_path)

    def on_stop(self) -> None:
        for client_id, record_type in self._subscriptions:
            self.unsubscribe_data(
                DataType(record_type),
                client_id=client_id,
            )


def add_live_custom_data(
    node: TradingNode,
    providers: Sequence[object],
    *,
    catalog_path: Path,
) -> None:
    """Register every stream-capable provider without disturbing existing clients."""
    capabilities: list[LiveCustomDataCapability] = []
    configured_client_names = set(node._config.data_clients)
    for provider in providers:
        describe_capability = getattr(provider, "live_data_capability", None)
        if describe_capability is None:
            continue
        capability = describe_capability()
        if not isinstance(capability, LiveCustomDataCapability):
            raise InvalidLiveCustomDataCapabilityError(
                "live_data_capability() must return LiveCustomDataCapability"
            )
        client_name = capability.client_name.value
        if client_name in configured_client_names:
            raise LiveDataClientConflictError(ClientId(client_name))
        configured_client_names.add(client_name)
        capabilities.append(capability)

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
            for record_type in capability.record_types
        )
    if subscriptions:
        node.trader.add_actor(
            _CustomDataCaptureActor(
                tuple(dict.fromkeys(subscriptions)),
                catalog_path,
            )
        )


__all__ = ["LiveDataClientConflictError", "add_live_custom_data"]
