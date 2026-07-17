"""Trader-owned Nautilus wiring for streaming Custom Data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import msgspec
import pandas as pd
from nautilus_trader.common.actor import Actor
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model import DataType
from nautilus_trader.model.identifiers import ClientId

from aegis_data.custom_data import (
    CustomDataProviderPort,
    InvalidLiveCustomDataCapabilityError,
    LiveCustomDataCapability,
    capture,
)

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


def build_live_sleeve_arrays(
    providers: Sequence[object],
    *,
    catalog_path: Path,
) -> SleeveArrays:
    """Build the complete live Sleeve array module."""
    return SleeveArrays.live(
        catalog_path=catalog_path,
        providers=_historical_providers_by_record_type(providers),
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
    providers: Sequence[object],
    *,
    catalog_path: Path,
) -> None:
    """Register every stream-capable provider without disturbing existing clients."""
    capabilities: list[LiveCustomDataCapability] = []
    configured_client_names = set(node._config.data_clients)
    for _provider, capability in _live_capabilities(providers):
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
            (client_id, record_type) for record_type in capability.record_types
        )
    if subscriptions:
        node.trader.add_actor(
            _CustomDataCaptureActor(
                tuple(dict.fromkeys(subscriptions)),
                catalog_path,
            )
        )


def _live_capabilities(
    providers: Sequence[object],
) -> tuple[tuple[object, LiveCustomDataCapability], ...]:
    capabilities: list[tuple[object, LiveCustomDataCapability]] = []
    for provider in providers:
        describe_capability = getattr(provider, "live_data_capability", None)
        if describe_capability is None:
            continue
        capability = describe_capability()
        if not isinstance(capability, LiveCustomDataCapability):
            raise InvalidLiveCustomDataCapabilityError(
                "live_data_capability() must return LiveCustomDataCapability"
            )
        capabilities.append((provider, capability))
    return tuple(capabilities)


def _historical_providers_by_record_type(
    providers: Sequence[object],
) -> dict[type[Data], list[CustomDataProviderPort[Any]]]:
    providers_by_record_type: dict[type[Data], list[CustomDataProviderPort[Any]]] = {}
    for provider, capability in _live_capabilities(providers):
        if getattr(provider, "request_records", None) is None:
            continue
        historical_provider = cast(CustomDataProviderPort[Any], provider)
        for record_type in capability.record_types:
            providers_by_record_type.setdefault(record_type, []).append(
                historical_provider
            )
    return providers_by_record_type


__all__ = [
    "LiveDataClientConflictError",
    "add_live_custom_data",
    "build_live_sleeve_arrays",
    "warm_live_custom_data",
]
