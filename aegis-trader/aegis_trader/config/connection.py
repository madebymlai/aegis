"""The Broker Connection — IBKR gateway port + account, read from the environment.

The broker connection is environment-specific and secret-ish — the account ID
especially — so it is *never* part of the version-controlled ``book.toml``.
:meth:`IBConnectionSettings.from_env` reads it from the process environment; the
resolved value is handed to the single IBKR adapter
(:func:`aegis_data.ibkr.live_clients`), which translates it into Nautilus's
stock dockerized-gateway client configs for the live ``TradingNode``.

There is **no mode**: paper and live are the same code path pointed at different
gateway ports, so the **port alone** distinguishes them.  ``IB_PORT`` and
``IB_ACCOUNT_ID`` are therefore both required and fail closed; the IBKR adapter
translates the port into Nautilus's dockerized ``trading_mode`` spelling.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_DEFAULT_CLIENT_ID = 1
_DEFAULT_TRADER_ID = "TRADER-001"


class ConnectionConfigError(ValueError):
    """The IBKR connection settings are missing or invalid in the environment."""


@dataclass(frozen=True)
class IBConnectionSettings:
    """Resolved IBKR connection facts for a live (paper or live) trader run."""

    port: int
    client_id: int
    account_id: str
    trader_id: str

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
    ) -> IBConnectionSettings:
        """Resolve connection settings from the environment.

        Reads ``IB_PORT`` / ``IB_CLIENT_ID`` / ``IB_ACCOUNT_ID`` /
        ``TRADER_ID``.  ``IB_PORT`` (the paper/live switch) and
        ``IB_ACCOUNT_ID`` are **required** and fail closed; client id and trader
        id fall back to defaults.
        """
        env = os.environ if env is None else env

        account_id = env.get("IB_ACCOUNT_ID")
        if not account_id:
            raise ConnectionConfigError(
                "IB_ACCOUNT_ID is required but is unset; "
                "refusing to use a placeholder account"
            )

        return cls(
            port=_required_int_env(env, "IB_PORT"),
            client_id=_int_env(env, "IB_CLIENT_ID", _DEFAULT_CLIENT_ID),
            account_id=account_id,
            trader_id=env.get("TRADER_ID", _DEFAULT_TRADER_ID),
        )


def _required_int_env(env: Mapping[str, str], key: str) -> int:
    raw = env.get(key)
    if raw is None:
        raise ConnectionConfigError(
            f"{key} is required (the port is the paper/live switch and Nautilus "
            "has no safe default); refusing to guess the gateway"
        )
    return _as_int(key, raw)


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    return _as_int(key, raw)


def _as_int(key: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConnectionConfigError(f"{key} must be an integer; got {raw!r}") from exc
