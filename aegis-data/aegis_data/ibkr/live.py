"""IBKR live client wiring — the Trader's one broker touch.

:func:`attach_live_clients` builds Nautilus's *stock*
``InteractiveBrokers{Data,Exec}ClientConfig`` with a Nautilus-managed Dockerized
IB Gateway and registers the stock live factories on a live ``TradingNode`` —
no custom adapter code or container lifecycle code (epic thesis).  The
ibapi-backed config/factory classes are imported lazily so importing this
module never requires ``ibapi``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol

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


def attach_live_clients(
    node: Any,
    connection: BrokerConnection,
    instrument_ids: Sequence[InstrumentId],
) -> None:
    """Wire IBKR's stock live data + exec clients onto *node* (before ``build()``).

    The single live-broker call the Trader's broker-neutral ``node.py`` makes:
    builds Nautilus's *stock* ``InteractiveBrokers{Data,Exec}ClientConfig`` —
    ``market_data_type=REALTIME``, a Nautilus-managed Dockerized IB Gateway, and
    an ``InstrumentProviderConfig`` whose ``load_ids`` are exactly the declared
    native ids (the data-only FX ``exchange:`` natives ride in here too) — and
    registers the stock live factories.  No custom adapter code: paper vs live is
    *only* ``connection.port``, translated here into the dockerized
    ``trading_mode``.

    The ibapi-backed config/factory classes are imported lazily so importing this
    module never needs ``ibapi`` (the same lazy boundary as the historic client).
    """
    import msgspec
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
    # Nautilus consumes ``data_clients``/``exec_clients`` from the node's stored
    # config at ``build()``; there is no public setter, so swap the (immutable)
    # config for one carrying the IBKR clients, then register the factories.
    node._config = msgspec.structs.replace(
        node._config,
        data_clients={IB_CLIENT_NAME: data_config},
        exec_clients={IB_CLIENT_NAME: exec_config},
    )
    node.add_data_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory(IB_CLIENT_NAME, InteractiveBrokersLiveExecClientFactory)


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
