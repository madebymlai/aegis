"""Book state behind a narrow port (ADR-0003, Wave B).

A *deep* port: it hides the multi-hop Nautilus reads the overlay needs —
NAV-in-base, total cash, cache health, and per-instrument realized weights —
behind four plain methods.  The sole adapter, :class:`NautilusBookState`,
implements it over Nautilus's own ``PortfolioFacade`` + ``CacheFacade`` read
interfaces, delegating the marking + base-currency conversion of realized
exposure to ``net_exposure(target_currency=base)`` and applying only the
position's sign.

One concern, one Nautilus implementation — so the Protocol and its adapter live
in one module.  The port/adapter file split is reserved for multi-impl concerns
(``bundles/``, ``observability/``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.objects import Currency
from nautilus_trader.portfolio.base import PortfolioFacade


@runtime_checkable
class BookStatePort(Protocol):
    """Reconciled book-state reads the rebalance overlay depends on."""

    def nav(self) -> float:
        """Net asset value in the book's base currency, summed across accounts."""
        ...

    def cash(self) -> float:
        """Total cash in the book's base currency, summed across accounts."""
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


class NautilusBookState:
    """BookStatePort backed by the Nautilus Portfolio + Cache read interfaces.

    Venue-agnostic (Wave D): NAV and cash sum the base-currency total over every
    reconciled account (``cache.accounts()``).  One IBKR account spanning many
    exchanges and a multi-venue backtest with one account per venue both reduce
    to the same aggregation — the book never names a single venue.
    """

    def __init__(
        self,
        *,
        portfolio: PortfolioFacade,
        cache: CacheFacade,
        base_currency: Currency,
        instr_to_figi: Mapping[str, str],
    ) -> None:
        self._portfolio = portfolio
        self._cache = cache
        self._base = base_currency
        self._instr_to_figi = instr_to_figi

    def nav(self) -> float:
        total = 0.0
        for account in self._cache.accounts():
            equity = self._portfolio.equity(account_id=account.id)
            money = equity.get(self._base) if equity else None
            if money is not None:
                total += float(money.as_double())
        return total

    def cash(self) -> float:
        total = 0.0
        for account in self._cache.accounts():
            money = account.balances_total().get(self._base)
            if money is not None:
                total += float(money.as_double())
        return total

    def is_cache_healthy(self) -> bool:
        return len(self._cache.instruments()) > 0

    def realized_weights(self) -> dict[str, float]:
        nav = self.nav()
        if nav <= 0:
            return {}
        weights: dict[str, float] = {}
        for position in self._cache.positions_open():
            figi = self._instr_to_figi.get(position.instrument_id.value)
            if figi is None:
                continue  # holding not covered by any sleeve
            exposure = self._portfolio.net_exposure(
                position.instrument_id, target_currency=self._base
            )
            if exposure is None:
                continue  # unpriced — no mark available
            signed = float(exposure.as_double())
            if position.is_short:
                signed = -signed
            weights[figi] = weights.get(figi, 0.0) + signed / nav
        return weights
