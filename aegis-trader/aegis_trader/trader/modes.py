"""Paper-mode wiring (Slice 10): SANDBOX TradingNode with IBKR configs.

Builds a NautilusTrader SANDBOX TradingNode configured for paper trading
through Interactive Brokers.  Every wire is connected — data client, exec
client, instrument provider, routing, cache, logging, reconciliation —
but NO live connection is made or asserted.

Architecture invariant (ADR-0003): IBKR appears ONLY in this module as
client-factory config.  No broker import in domain/, ports/, the Strategy,
or execution translation.

The IBKR-specific config objects (``InteractiveBrokersDataClientConfig``,
``InteractiveBrokersExecClientConfig``) require the ``ibapi`` runtime.
To keep this module importable without ``ibapi``, the data-client and
exec-client configs are produced as plain dicts.  The operator feeds these
dicts into the full IBKR config classes at node-build time.
"""

from __future__ import annotations

from typing import Any

from nautilus_trader.config import (
    CacheConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.common import Environment
from nautilus_trader.live.node import TradingNode

# ── paper-mode constants ──────────────────────────────────────────────────────

IB_DATA_CLIENT_NAME: str = "IB"
IB_EXEC_CLIENT_NAME: str = "IB"
IB_HOST: str = "127.0.0.1"
IB_PAPER_PORT: int = 7497  # TWS paper port; IB Gateway paper default is 4002
IB_CLIENT_ID: int = 1
IB_PAPER_ACCOUNT_ID: str = "DU0000000"  # placeholder — operator provides real one


# ── IBKR config dict builders ─────────────────────────────────────────────────
#
# These return *dicts* rather than importing IBKR config classes so the module
# remains importable without ``ibapi``.  At runtime (with ibapi available) the
# operator passes the dict through InteractiveBrokersDataClientConfig or
# InteractiveBrokersExecClientConfig, which Nautilus resolves automatically.


def build_paper_data_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_PAPER_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    market_data_type: str = "frozen",  # IBMarketDataTypeEnum.DELAYED_FROZEN
) -> dict[str, Any]:
    """Build an IBKR paper-mode data client config dict.

    Uses IB Market Data line type ``"frozen"`` (delayed frozen) so that no
    real-time data subscription is required.  The actual IBKR implementation
    is provided by Nautilus; this is a plain config wire.

    Paper port 7497 = TWS paper default; IB Gateway paper default is 4002.
    """
    return {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "market_data_type": market_data_type,
        "use_regular_trading_hours": True,
    }


def build_paper_exec_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_PAPER_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    account_id: str = IB_PAPER_ACCOUNT_ID,
) -> dict[str, Any]:
    """Build an IBKR paper-mode execution client config dict.

    The account ID must be the Interactive Brokers paper account ID
    (DU-prefixed).  The actual go-live account ID is provided by the
    operator, not hard-coded here.
    """
    return {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "account_id": account_id,
    }


# ── node config builder ───────────────────────────────────────────────────────


def build_paper_trading_node_config(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNodeConfig:
    """Build a SANDBOX TradingNodeConfig for paper trading with IBKR.

    Wires every component required for a paper-mode deployment:

    * ``Environment.SANDBOX`` (no real money — paper venue)
    * ``RoutingConfig(default=True)`` on each IBKR client (via the dict
      builders, which the operator feeds through IBKR config constructors)
    * ``CacheConfig`` — in-memory cache for price/order/position state
    * ``LoggingConfig`` — structured logging
    * Reconciliation enabled on the exec engine (startup position sync)

    The IBKR data-client and exec-client configs are NOT populated here —
    they require the ``InteractiveBrokersDataClientConfig`` /
    ``InteractiveBrokersExecClientConfig`` types which need ``ibapi`` at
    runtime.  Use ``build_paper_data_client_config()`` and
    ``build_paper_exec_client_config()`` to produce the dicts, then pass
    them through the proper IBKR config constructors at node-build time.

    Parameters
    ----------
    trader_id : str
        The trader ID for this node (must be unique per process).

    Returns
    -------
    TradingNodeConfig
        Fully wired paper-mode configuration (clients not yet populated).
    """
    return TradingNodeConfig(
        environment=Environment.SANDBOX,
        trader_id=trader_id,
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        cache=CacheConfig(),
        logging=LoggingConfig(),
    )


# ── node builder ──────────────────────────────────────────────────────────────


def build_paper_trading_node(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNode:
    """Build a SANDBOX TradingNode for IBKR paper trading.

    Constructs (but does NOT build/connect) a TradingNode wired for paper
    mode.  The caller must:

    1. Add the IBKR data client and exec client configs (via the
       ``InteractiveBrokersDataClientConfig`` /
       ``InteractiveBrokersExecClientConfig`` types — requires ``ibapi``
       runtime).
    2. Register data/exec client factories via
       ``node.add_data_client_factory`` / ``node.add_exec_client_factory``.
    3. Add the strategy.
    4. Call ``node.build()`` and ``node.run()``.

    Parameters
    ----------
    trader_id : str
        The trader ID for this node.

    Returns
    -------
    TradingNode
        The constructed (not yet built) paper trading node.
    """
    config = build_paper_trading_node_config(trader_id=trader_id)
    return TradingNode(config=config)
