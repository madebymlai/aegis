"""Operator-facing configuration — declarative book spec + connection settings.

``book.toml`` (version-controllable, non-secret) decodes to the domain
``BookConfig``; the IBKR Broker Connection + account come from the environment
(secret), never committed.  This package is the seam between the operator's
files/env and the live node in ``trader/node.py``.
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
