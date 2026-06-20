"""Operator-facing configuration — declarative book spec + connection settings.

``book.toml`` (version-controllable, non-secret) decodes to the domain
``BookConfig``; IBKR connection + account come from the environment (secret),
never committed.  This package is the seam between the operator's files/env and
the Nautilus node builders in ``trader/modes.py``.
"""

from aegis_trader.config.book import (
    BookConfigError,
    find_book_config,
    load_book_config,
)
from aegis_trader.config.connection import (
    ConnectionConfigError,
    IBConnectionSettings,
)

__all__ = [
    "BookConfigError",
    "ConnectionConfigError",
    "IBConnectionSettings",
    "find_book_config",
    "load_book_config",
]
