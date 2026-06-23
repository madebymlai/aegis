"""Unit tests for the IBKR Broker Connection — pure, zero Nautilus.

Connection + account are *secret-ish, environment-specific* and never live in the
version-controlled book.toml: they are read from the environment and handed to the
single IBKR adapter.  There is no mode — ``IB_PORT`` (the paper/live switch) and
``IB_ACCOUNT_ID`` are both required and fail closed when absent, so the live path
can never guess the gateway or silently run a placeholder account.
"""

from __future__ import annotations

import pytest

from aegis_trader.config import ConnectionConfigError, IBConnectionSettings


def test_resolves_account_and_port_from_env_with_defaults():
    """Account + port from env; host, client id, and trader id default."""
    settings = IBConnectionSettings.from_env(
        env={"IB_ACCOUNT_ID": "DU1234567", "IB_PORT": "4002"},
    )

    assert settings.account_id == "DU1234567"
    assert settings.port == 4002
    assert settings.host == "127.0.0.1"
    assert settings.client_id == 1
    assert settings.trader_id == "TRADER-001"
    assert settings.dockerized_gateway is None


def test_port_is_the_paper_live_switch():
    """Paper vs live is only the port — both resolve through the same path."""
    paper = IBConnectionSettings.from_env(
        env={"IB_ACCOUNT_ID": "DU1234567", "IB_PORT": "4002"},
    )
    live = IBConnectionSettings.from_env(
        env={"IB_ACCOUNT_ID": "U7654321", "IB_PORT": "4001"},
    )
    assert (paper.port, live.port) == (4002, 4001)


def test_env_overrides_are_honoured():
    settings = IBConnectionSettings.from_env(env={
        "IB_ACCOUNT_ID": "DU1234567",
        "IB_HOST": "10.0.0.5",
        "IB_PORT": "7497",  # TWS paper port
        "IB_CLIENT_ID": "9",
        "TRADER_ID": "BOOK-EU-01",
    })
    assert settings.host == "10.0.0.5"
    assert settings.port == 7497
    assert settings.client_id == 9
    assert settings.trader_id == "BOOK-EU-01"


def test_missing_port_fails_closed():
    """No IB_PORT -> refuse to run (the port is the paper/live switch, no default)."""
    with pytest.raises(ConnectionConfigError, match="IB_PORT"):
        IBConnectionSettings.from_env(env={"IB_ACCOUNT_ID": "DU1234567"})


def test_missing_account_id_fails_closed():
    """No IB_ACCOUNT_ID -> refuse to run (no placeholder account)."""
    with pytest.raises(ConnectionConfigError, match="IB_ACCOUNT_ID"):
        IBConnectionSettings.from_env(env={"IB_PORT": "4002"})


def test_non_integer_port_fails_closed():
    with pytest.raises(ConnectionConfigError, match="IB_PORT"):
        IBConnectionSettings.from_env(env={
            "IB_ACCOUNT_ID": "DU1234567",
            "IB_PORT": "not-a-number",
        })
