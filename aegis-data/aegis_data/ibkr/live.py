"""IBKR live client configuration — the Trader's one broker touch.

:func:`live_clients` builds Nautilus's *stock*
``InteractiveBrokers{Data,Exec}ClientConfig`` with a Nautilus-managed Dockerized
IB Gateway.  Its returned value contributes those configs before a live node is
constructed and registers the stock factories afterward — no private node access,
custom adapter code, or container lifecycle code (epic thesis).  The
ibapi-backed config/factory classes are imported lazily so importing this
module never requires ``ibapi``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from nautilus_trader.config import LiveDataClientConfig, LiveExecClientConfig
from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.ibkr.symbology import mic_instrument_provider_config

# Nautilus client name shared by the IBKR data + exec clients (the key the
# registered factories resolve against).
IB_CLIENT_NAME = "INTERACTIVE_BROKERS"


class BrokerConnection(Protocol):
    """The Trader-owned Broker Connection this adapter translates into IBKR
    client configs (the connection value object lives in the Trader; this adapter
    depends only on its shape, never imports it — DIP).

    The Trader stays broker-neutral and supplies only the gateway port/account
    facts.  This adapter is the only place that maps IBKR's paper/live ports to
    Nautilus's dockerized ``trading_mode`` spelling.
    """

    port: int
    client_id: int
    account_id: str


@dataclass(frozen=True)
class BrokerClients:
    """IBKR client configs plus the factories that consume them at node build."""

    data_config: LiveDataClientConfig
    exec_config: LiveExecClientConfig
    data_factory: type[LiveDataClientFactory]
    exec_factory: type[LiveExecClientFactory]

    @property
    def data_clients(self) -> dict[str, LiveDataClientConfig]:
        return {IB_CLIENT_NAME: self.data_config}

    @property
    def exec_clients(self) -> dict[str, LiveExecClientConfig]:
        return {IB_CLIENT_NAME: self.exec_config}

    def register(self, node: Any) -> None:
        """Register the stock factories after the complete node is constructed."""
        node.add_data_client_factory(IB_CLIENT_NAME, self.data_factory)
        node.add_exec_client_factory(IB_CLIENT_NAME, self.exec_factory)


def live_clients(
    connection: BrokerConnection,
    instrument_ids: Sequence[InstrumentId],
) -> BrokerClients:
    """Build IBKR's stock live client contribution for a complete node config.

    The single live-broker call the Trader's broker-neutral ``node.py`` makes:
    builds Nautilus's *stock* ``InteractiveBrokers{Data,Exec}ClientConfig`` —
    ``market_data_type=REALTIME``, a Nautilus-managed Dockerized IB Gateway, and
    an ``InstrumentProviderConfig`` whose ``load_ids`` are exactly the declared
    native ids (the data-only FX ``exchange:`` natives ride in here too).  The
    returned value registers the corresponding stock factories through the node's
    public API after construction.  Paper vs live is *only* ``connection.port``,
    translated here into the dockerized ``trading_mode``.

    The ibapi-backed config/factory classes are imported lazily so importing this
    module never needs ``ibapi`` (the same lazy boundary as the historic client).
    """
    from nautilus_trader.adapters.interactive_brokers.config import (
        IBMarketDataTypeEnum,
        InteractiveBrokersDataClientConfig,
        InteractiveBrokersExecClientConfig,
    )
    from nautilus_trader.adapters.interactive_brokers.factories import (
        InteractiveBrokersLiveDataClientFactory,
        InteractiveBrokersLiveExecClientFactory,
    )

    provider = mic_instrument_provider_config(
        load_ids=(instrument_id.value for instrument_id in instrument_ids),
    )
    endpoint = _gateway_endpoint(connection)
    data_config = InteractiveBrokersDataClientConfig(
        ibg_client_id=connection.client_id,
        market_data_type=IBMarketDataTypeEnum.REALTIME,
        use_regular_trading_hours=True,
        instrument_provider=provider,
        **endpoint,
    )
    exec_config = InteractiveBrokersExecClientConfig(
        ibg_client_id=connection.client_id,
        account_id=connection.account_id,
        instrument_provider=provider,
        **endpoint,
    )
    return BrokerClients(
        data_config=data_config,
        exec_config=exec_config,
        data_factory=InteractiveBrokersLiveDataClientFactory,
        exec_factory=InteractiveBrokersLiveExecClientFactory,
    )


_GATEWAY_TRADING_MODE: dict[int, Literal["paper", "live"]] = {
    4002: "paper",
    4001: "live",
}


def _trading_mode_for_port(port: int) -> Literal["paper", "live"]:
    try:
        return _GATEWAY_TRADING_MODE[port]
    except KeyError as exc:
        raise ValueError(
            "IB_PORT must be 4002 (paper) or 4001 (live) for the dockerized "
            f"gateway; got {port}"
        ) from exc


def _gateway_endpoint(connection: BrokerConnection) -> dict[str, Any]:
    """The Dockerized IB Gateway kwargs shared by both IBKR client configs."""
    from nautilus_trader.adapters.interactive_brokers.config import (
        DockerizedIBGatewayConfig,
    )

    gateway = DockerizedIBGatewayConfig(
        trading_mode=_trading_mode_for_port(connection.port),
        read_only_api=False,
    )
    return {"dockerized_gateway": gateway}
