"""Unit tests for Slice 10: paper-mode wiring (IBKR SANDBOX, no live connection).

Validates that the paper-mode configuration functions build a correctly
configured SANDBOX TradingNodeConfig with cache, logging, and reconciliation —
all without requiring a live IBKR connection or the ``ibapi`` package.

These are *wiring* tests: they assert that the right components are present
and correctly configured, not that the node connects to IBKR.

The IBKR-specific data-client and exec-client configs are tested as dict
builders — the actual ``InteractiveBrokersDataClientConfig`` /
``InteractiveBrokersExecClientConfig`` constructors require ``ibapi`` and
are tested separately in an integration environment.
"""

from __future__ import annotations

from nautilus_trader.config import (
    CacheConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.common import Environment

from aegis_trader.trader.modes import (
    build_paper_trading_node,
    build_paper_trading_node_config,
    build_paper_data_client_config,
    build_paper_exec_client_config,
    IB_CLIENT_ID,
    IB_HOST,
    IB_PAPER_ACCOUNT_ID,
    IB_PAPER_PORT,
)


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
    """The paper TradingNodeConfig MUST include a cache config."""
    cfg = build_paper_trading_node_config()
    assert cfg.cache is not None, (
        "Expected cache config to be set"
    )
    assert isinstance(cfg.cache, CacheConfig)


def test_paper_node_config_has_logging():
    """The paper TradingNodeConfig MUST include a logging config."""
    cfg = build_paper_trading_node_config()
    assert cfg.logging is not None, (
        "Expected logging config to be set"
    )
    assert isinstance(cfg.logging, LoggingConfig)


def test_paper_node_config_has_reconciliation():
    """The paper TradingNodeConfig MUST enable reconciliation on the exec engine."""
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
    """The paper IBKR data client dict MUST accept custom host and port."""
    cfg = build_paper_data_client_config(ibg_host="10.0.0.1", ibg_port=4002)
    assert cfg["ibg_host"] == "10.0.0.1"
    assert cfg["ibg_port"] == 4002


def test_paper_data_client_config_custom_client_id():
    """The paper IBKR data client dict MUST accept a custom client ID."""
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
    """The paper IBKR exec client dict MUST accept a custom account ID."""
    cfg = build_paper_exec_client_config(account_id="DU1234567")
    assert cfg["account_id"] == "DU1234567"


# --------------------------------------------------------------------------- #
# node construction test (no live connection required)
# --------------------------------------------------------------------------- #

def test_paper_trading_node_constructs():
    """TradingNode constructs without error — no IBKR connection required."""
    try:
        node = build_paper_trading_node()
    except Exception as exc:
        assert False, f"build_paper_trading_node() raised {type(exc).__name__}: {exc}"
    else:
        assert node is not None
