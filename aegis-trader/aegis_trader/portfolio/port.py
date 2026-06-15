"""BookStatePort — the Trader's narrow view of reconciled book state.

A *deep* port (ADR-0003): it hides the multi-hop Nautilus reads the overlay
needs — NAV-in-base, total cash, cache health, and per-instrument realized
weights — behind four plain methods.  The Nautilus-backed adapter
(``portfolio/nautilus.py``) implements it over Nautilus's own ``PortfolioFacade``
+ ``CacheFacade`` read interfaces, so the Strategy never reaches into the kernel
for book state and the Demeter train-wrecks live in exactly one place.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BookStatePort(Protocol):
    """Reconciled book-state reads the rebalance overlay depends on."""

    def nav(self) -> float:
        """Account net asset value in the book's base currency."""
        ...

    def cash(self) -> float:
        """Total cash balance in the book's base currency."""
        ...

    def is_cache_healthy(self) -> bool:
        """Whether the reconciled cache holds instruments (startup integrity)."""
        ...

    def realized_weights(self) -> dict[str, float]:
        """Signed realized weight (fraction of NAV) per covered FIGI.

        The marking and base-currency conversion of each open position's net
        exposure is delegated to Nautilus; the sign comes from the position.
        """
        ...
