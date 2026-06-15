"""Unit tests for Slice 10 (paper-mode) and Slice 11 (live-mode) wiring.

Validates that paper-mode (SANDBOX) and live-mode (LIVE) configuration
functions build correctly configured TradingNodeConfigs with cache,
logging, and reconciliation — all without requiring a live IBKR
connection or the ``ibapi`` package.

These are *wiring* tests: they assert that the right components are present
and correctly configured, not that the node connects to IBKR.

The IBKR-specific data-client and exec-client configs are tested as dict
builders — the actual ``InteractiveBrokersDataClientConfig`` /
``InteractiveBrokersExecClientConfig`` constructors require ``ibapi`` and
are tested separately in an integration environment.
"""

from __future__ import annotations

import asyncio

from nautilus_trader.config import (
    CacheConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.common import Environment

from nautilus_trader.model.enums import TimeInForce

from aegis_trader.trader.modes import (
    build_backtest_engine_config,
    build_paper_trading_node,
    build_paper_trading_node_config,
    build_paper_data_client_config,
    build_paper_exec_client_config,
    build_live_trading_node,
    build_live_trading_node_config,
    build_live_data_client_config,
    build_live_exec_client_config,
    build_risk_engine_config,
    fill_time_in_force_for_mode,
    IB_CLIENT_ID,
    IB_HOST,
    IB_LIVE_ACCOUNT_ID,
    IB_LIVE_PORT,
    IB_PAPER_ACCOUNT_ID,
    IB_PAPER_PORT,
)


# --------------------------------------------------------------------------- #
# next-close TIF per mode (A2 / ADR-0001)
# --------------------------------------------------------------------------- #

def test_backtest_mode_uses_plain_market():
    """Backtest fills via a plain MARKET (no session TIF)."""
    assert fill_time_in_force_for_mode("backtest") is None


def test_paper_and_live_modes_use_market_on_close():
    """Paper/live carry AT_THE_CLOSE (Market-on-Close) per ADR-0001."""
    assert fill_time_in_force_for_mode("paper") == TimeInForce.AT_THE_CLOSE
    assert fill_time_in_force_for_mode("live") == TimeInForce.AT_THE_CLOSE


def test_unknown_mode_rejected():
    import pytest
    with pytest.raises(ValueError, match="unknown mode"):
        fill_time_in_force_for_mode("sandbox")


# --------------------------------------------------------------------------- #
# RiskEngine wiring (A4) + backtest mode runner (A5)
# --------------------------------------------------------------------------- #

def test_risk_engine_config_carries_rate_limits_and_is_not_bypassed():
    cfg = build_risk_engine_config()
    assert cfg.bypass is False
    assert cfg.max_order_submit_rate == "10/00:00:01"
    assert cfg.max_order_modify_rate == "10/00:00:01"


def test_paper_node_wires_risk_engine():
    cfg = build_paper_trading_node_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False


def test_live_node_wires_risk_engine():
    cfg = build_live_trading_node_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False


def test_backtest_engine_config_mirrors_risk_wiring():
    cfg = build_backtest_engine_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False
    assert cfg.risk_engine.max_order_submit_rate == "10/00:00:01"


# --------------------------------------------------------------------------- #
# structural config tests (no IBKR imports needed)
# --------------------------------------------------------------------------- #

def test_paper_node_config_has_sandbox_environment():
    """The paper TradingNodeConfig MUST use Environment.SANDBOX."""
    cfg = build_paper_trading_node_config()
    assert cfg.environment == Environment.SANDBOX, (
        f"Expected SANDBOX, got {cfg.environment}"
    )


def test_paper_node_config_has_cache():
    cfg = build_paper_trading_node_config()
    assert cfg.cache is not None, (
        "Expected cache config to be set"
    )
    assert isinstance(cfg.cache, CacheConfig)


def test_paper_node_config_has_logging():
    cfg = build_paper_trading_node_config()
    assert cfg.logging is not None, (
        "Expected logging config to be set"
    )
    assert isinstance(cfg.logging, LoggingConfig)


def test_paper_node_config_has_reconciliation():
    cfg = build_paper_trading_node_config()
    assert cfg.exec_engine.reconciliation is True, (
        f"Expected reconciliation=True, got {cfg.exec_engine.reconciliation}"
    )


def test_paper_node_config_is_msgspec_serializable():
    """TradingNodeConfig survives a JSON round-trip."""
    cfg = build_paper_trading_node_config()
    cfg_json = cfg.json()
    loaded = TradingNodeConfig.parse(cfg_json)
    assert loaded.environment == cfg.environment
    assert loaded.trader_id == cfg.trader_id
    assert loaded.cache is not None
    assert loaded.logging is not None
    assert loaded.exec_engine.reconciliation is True


# --------------------------------------------------------------------------- #
# IBKR dict config tests (no ibapi needed — just dict assertions)
# --------------------------------------------------------------------------- #

def test_paper_data_client_config_defaults():
    """The paper IBKR data client dict defaults to frozen market data on the paper port."""
    cfg = build_paper_data_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_PAPER_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["market_data_type"] == "frozen"


def test_paper_data_client_config_custom_host():
    cfg = build_paper_data_client_config(ibg_host="10.0.0.1", ibg_port=4002)
    assert cfg["ibg_host"] == "10.0.0.1"
    assert cfg["ibg_port"] == 4002


def test_paper_data_client_config_custom_client_id():
    cfg = build_paper_data_client_config(ibg_client_id=99)
    assert cfg["ibg_client_id"] == 99


def test_paper_exec_client_config_defaults():
    """The paper IBKR exec client dict MUST use paper port and DU-prefixed account."""
    cfg = build_paper_exec_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_PAPER_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["account_id"].startswith("DU"), (
        f"Expected DU-prefixed paper account, got {cfg['account_id']!r}"
    )
    assert cfg["account_id"] == IB_PAPER_ACCOUNT_ID


def test_paper_exec_client_config_custom_account():
    cfg = build_paper_exec_client_config(account_id="DU1234567")
    assert cfg["account_id"] == "DU1234567"


# --------------------------------------------------------------------------- #
# node construction test (no live connection required)
# --------------------------------------------------------------------------- #

def test_paper_trading_node_constructs():
    """TradingNode constructs without error."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            node = build_paper_trading_node()
        except Exception as exc:
            assert False, f"build_paper_trading_node() raised {type(exc).__name__}: {exc}"
        else:
            assert node is not None
    finally:
        loop.close()


# --------------------------------------------------------------------------- #
# LIVE-mode structural config tests (Slice 11 — no IBKR imports needed)
# --------------------------------------------------------------------------- #

def test_live_node_config_has_live_environment():
    """The live TradingNodeConfig MUST use Environment.LIVE."""
    cfg = build_live_trading_node_config()
    assert cfg.environment == Environment.LIVE, (
        f"Expected LIVE, got {cfg.environment}"
    )


def test_live_node_config_has_cache():
    cfg = build_live_trading_node_config()
    assert cfg.cache is not None
    assert isinstance(cfg.cache, CacheConfig)


def test_live_node_config_has_logging():
    cfg = build_live_trading_node_config()
    assert cfg.logging is not None
    assert isinstance(cfg.logging, LoggingConfig)


def test_live_node_config_has_reconciliation():
    cfg = build_live_trading_node_config()
    assert cfg.exec_engine.reconciliation is True, (
        f"Expected reconciliation=True, got {cfg.exec_engine.reconciliation}"
    )


def test_live_node_config_is_msgspec_serializable():
    cfg = build_live_trading_node_config()
    cfg_json = cfg.json()
    loaded = TradingNodeConfig.parse(cfg_json)
    assert loaded.environment == cfg.environment
    assert loaded.trader_id == cfg.trader_id
    assert loaded.cache is not None
    assert loaded.logging is not None
    assert loaded.exec_engine.reconciliation is True


# --------------------------------------------------------------------------- #
# LIVE-mode IBKR dict config tests (no ibapi needed)
# --------------------------------------------------------------------------- #

def test_live_data_client_config_defaults():
    """The live IBKR data client dict defaults to realtime on the live port."""
    cfg = build_live_data_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_LIVE_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["market_data_type"] == "realtime"


def test_live_data_client_config_custom_host():
    cfg = build_live_data_client_config(ibg_host="10.0.0.1", ibg_port=4001)
    assert cfg["ibg_host"] == "10.0.0.1"
    assert cfg["ibg_port"] == 4001


def test_live_data_client_config_custom_client_id():
    cfg = build_live_data_client_config(ibg_client_id=99)
    assert cfg["ibg_client_id"] == 99


def test_live_exec_client_config_defaults():
    """The live IBKR exec client dict MUST use live port and non-DU account."""
    cfg = build_live_exec_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_LIVE_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert not cfg["account_id"].startswith("DU"), (
        f"Expected non-DU live account, got {cfg['account_id']!r}"
    )
    assert cfg["account_id"] == IB_LIVE_ACCOUNT_ID


def test_live_exec_client_config_custom_account():
    cfg = build_live_exec_client_config(account_id="U1234567")
    assert cfg["account_id"] == "U1234567"


def test_live_trading_node_constructs():
    """TradingNode constructs without error."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            node = build_live_trading_node()
        except Exception as exc:
            assert False, f"build_live_trading_node() raised {type(exc).__name__}: {exc}"
        else:
            assert node is not None
    finally:
        loop.close()
