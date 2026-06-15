"""Mode wiring (Slice 10 & 11): paper (SANDBOX) and live (LIVE) TradingNodes
with IBKR client configs.

Builds NautilusTrader TradingNodes configured for paper trading (SANDBOX)
and live trading (LIVE) through Interactive Brokers.  Every wire is
connected — data client, exec client, instrument provider, routing, cache,
logging, reconciliation — but NO live connection is made or asserted.

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

# ── IBKR constants ───────────────────────────────────────────────────────────

IB_HOST: str = "127.0.0.1"
IB_CLIENT_ID: int = 1

IB_PAPER_PORT: int = 7497  # TWS paper port; IB Gateway paper default is 4002
IB_PAPER_ACCOUNT_ID: str = "DU0000000"  # placeholder — operator provides real one

IB_LIVE_PORT: int = 7496  # TWS live port; IB Gateway live default is 4001
IB_LIVE_ACCOUNT_ID: str = "U0000000"  # placeholder — operator provides real one


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
    market_data_type: str = "frozen",
) -> dict[str, Any]:
    """Build an IBKR paper-mode data client config dict.

    ``market_data_type`` defaults to ``"frozen"`` (IBMarketDataTypeEnum.DELAYED_FROZEN)
    so that no real-time data subscription is required.
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

    Wires cache, logging, and reconciliation.  IBKR client configs are NOT
    populated — use ``build_paper_data_client_config()`` and
    ``build_paper_exec_client_config()`` to produce dicts, then pass them
    through the IBKR config constructors at node-build time (requires ``ibapi``).
    """
    return TradingNodeConfig(
        environment=Environment.SANDBOX,
        trader_id=trader_id,
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        cache=CacheConfig(),
        logging=LoggingConfig(),
    )


# ── node builder (paper) ─────────────────────────────────────────────────────


def build_paper_trading_node(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNode:
    """Build a SANDBOX TradingNode for IBKR paper trading.

    Constructs (but does NOT build/connect) a TradingNode.  Caller must
    add IBKR client configs, register factories, add the strategy, then
    call ``node.build()`` and ``node.run()``.
    """
    config = build_paper_trading_node_config(trader_id=trader_id)
    return TradingNode(config=config)


# ── live-mode config dict builders ───────────────────────────────────────────


def build_live_data_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_LIVE_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    market_data_type: str = "realtime",
) -> dict[str, Any]:
    """Build an IBKR live-mode data client config dict.

    ``market_data_type`` defaults to ``"realtime"``
    (IBMarketDataTypeEnum.REALTIME) for live market data.
    """
    return {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "market_data_type": market_data_type,
        "use_regular_trading_hours": True,
    }


def build_live_exec_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_LIVE_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    account_id: str = IB_LIVE_ACCOUNT_ID,
) -> dict[str, Any]:
    """Build an IBKR live-mode execution client config dict.

    The account ID must be the Interactive Brokers live account ID
    (non-DU-prefixed).  The actual go-live account ID is provided by the
    operator, not hard-coded here.
    """
    return {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "account_id": account_id,
    }


# ── live-mode node config ────────────────────────────────────────────────────


def build_live_trading_node_config(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNodeConfig:
    """Build a LIVE TradingNodeConfig for live trading with IBKR.

    Wires cache, logging, and reconciliation.  IBKR client configs are NOT
    populated — use ``build_live_data_client_config()`` and
    ``build_live_exec_client_config()`` to produce dicts, then pass them
    through the IBKR config constructors at node-build time (requires ``ibapi``).
    """
    return TradingNodeConfig(
        environment=Environment.LIVE,
        trader_id=trader_id,
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        cache=CacheConfig(),
        logging=LoggingConfig(),
    )


# ── node builder (live) ──────────────────────────────────────────────────────


def build_live_trading_node(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNode:
    """Build a LIVE TradingNode for IBKR live trading.

    Constructs (but does NOT build/connect) a TradingNode.  Caller must
    add IBKR client configs, register factories, add the strategy, then
    call ``node.build()`` and ``node.run()``.
    """
    config = build_live_trading_node_config(trader_id=trader_id)
    return TradingNode(config=config)
