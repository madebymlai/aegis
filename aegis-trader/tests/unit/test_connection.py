"""Unit tests for IBKR connection settings — pure, zero Nautilus.

Connection + account are *secret-ish, environment-specific* and never live in
the version-controlled book.toml: they are read from the environment and feed
the node builders in ``trader/modes.py``.  ``account_id`` is required and fails
closed when absent, so the live path can never silently run a placeholder
account.
"""

from __future__ import annotations

import pytest

from aegis_trader.config import ConnectionConfigError, IBConnectionSettings


def test_paper_defaults_with_account_from_env():
    """Paper mode: account from env, everything else a sensible default."""
    settings = IBConnectionSettings.from_env(
        "paper", env={"IB_ACCOUNT_ID": "DU1234567"},
    )

    assert settings.account_id == "DU1234567"
    assert settings.host == "127.0.0.1"
    assert settings.port == 7497  # TWS paper
    assert settings.client_id == 1
    assert settings.trader_id == "TRADER-001"


def test_live_mode_defaults_to_live_port():
    settings = IBConnectionSettings.from_env(
        "live", env={"IB_ACCOUNT_ID": "U7654321"},
    )
    assert settings.port == 7496  # TWS live


def test_env_overrides_are_honoured():
    settings = IBConnectionSettings.from_env("paper", env={
        "IB_ACCOUNT_ID": "DU1234567",
        "IB_HOST": "10.0.0.5",
        "IB_PORT": "4002",  # IB Gateway paper
        "IB_CLIENT_ID": "9",
        "TRADER_ID": "BOOK-EU-01",
    })
    assert settings.host == "10.0.0.5"
    assert settings.port == 4002
    assert settings.client_id == 9
    assert settings.trader_id == "BOOK-EU-01"


def test_missing_account_id_fails_closed():
    """No IB_ACCOUNT_ID -> refuse to run (no placeholder account)."""
    with pytest.raises(ConnectionConfigError, match="IB_ACCOUNT_ID"):
        IBConnectionSettings.from_env("paper", env={})


def test_unknown_mode_fails_closed():
    with pytest.raises(ConnectionConfigError, match="unknown mode"):
        IBConnectionSettings.from_env("backtest", env={"IB_ACCOUNT_ID": "X"})


def test_non_integer_port_fails_closed():
    with pytest.raises(ConnectionConfigError, match="IB_PORT"):
        IBConnectionSettings.from_env("paper", env={
            "IB_ACCOUNT_ID": "DU1234567",
            "IB_PORT": "not-a-number",
        })
