"""IBKR connection + account settings, read from the environment.

The broker connection is environment-specific and secret-ish — the account ID
especially — so it is *never* part of the version-controlled ``book.toml``.
``IBConnectionSettings.from_env`` reads it from the process environment and the
result feeds the node builders in ``trader/modes.py``; ``account_id`` is
required and fails closed, so the live path can never run a placeholder.

Port defaults follow TWS conventions per mode (paper 7497, live 7496); IB
Gateway users override via ``IB_PORT``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_CLIENT_ID = 1
_DEFAULT_TRADER_ID = "TRADER-001"
_DEFAULT_PORT: Mapping[str, int] = {"paper": 7497, "live": 7496}


class ConnectionConfigError(ValueError):
    """The IBKR connection settings are missing or invalid in the environment."""


@dataclass(frozen=True)
class IBConnectionSettings:
    """Resolved IBKR connection for a paper/live run."""

    host: str
    port: int
    client_id: int
    account_id: str
    trader_id: str

    @classmethod
    def from_env(
        cls,
        mode: str,
        *,
        env: Mapping[str, str] | None = None,
    ) -> IBConnectionSettings:
        """Resolve connection settings for *mode* (``"paper"`` or ``"live"``).

        Reads ``IB_HOST`` / ``IB_PORT`` / ``IB_CLIENT_ID`` / ``IB_ACCOUNT_ID`` /
        ``TRADER_ID``.  Only ``account_id`` is required; the rest fall back to
        mode-aware defaults.
        """
        if mode not in _DEFAULT_PORT:
            raise ConnectionConfigError(
                f"unknown mode {mode!r}; expected 'paper' or 'live'"
            )
        env = os.environ if env is None else env

        account_id = env.get("IB_ACCOUNT_ID")
        if not account_id:
            raise ConnectionConfigError(
                "IB_ACCOUNT_ID is required for a "
                f"{mode} run but is unset; refusing to use a placeholder account"
            )

        return cls(
            host=env.get("IB_HOST", _DEFAULT_HOST),
            port=_int_env(env, "IB_PORT", _DEFAULT_PORT[mode]),
            client_id=_int_env(env, "IB_CLIENT_ID", _DEFAULT_CLIENT_ID),
            account_id=account_id,
            trader_id=env.get("TRADER_ID", _DEFAULT_TRADER_ID),
        )


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConnectionConfigError(f"{key} must be an integer; got {raw!r}") from exc
