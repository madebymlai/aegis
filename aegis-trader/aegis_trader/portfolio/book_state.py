"""Book state behind a narrow port (ADR-0003, Wave B).

A *deep* port: it hides the multi-hop Nautilus reads the overlay needs —
NAV-in-base, total cash, cache health, and per-instrument realized weights —
behind four plain methods.  The sole adapter, :class:`NautilusBookState`,
implements it over Nautilus's own ``PortfolioFacade`` + ``CacheFacade`` read
interfaces: it marks each open position with ``net_exposure`` (in the position's
*native* currency) and converts that to base via the cache's venue-agnostic mark
xrate — the *same* FX source the sizer uses — applying only the position's sign.

Why not ``net_exposure(target_currency=base)``?  That path converts through the
cache's per-venue quote table, which only resolves when an FX ``CurrencyPair``
is registered *on the position's own venue*.  A commingled book spans many
venues (XLON, XNYS, …) while FX is one rate; sourcing the base conversion from
the venue-agnostic mark xrate keeps valuation working on every venue and uses
exactly the rate the sizer already trades against.

One concern, one Nautilus implementation — so the Protocol and its adapter live
in one module.  The port/adapter file split is reserved for multi-impl concerns
(``bundles/``, ``observability/``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from nautilus_trader.cache.base import CacheFacade
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.portfolio.base import PortfolioFacade

from aegis_runtime import InstrumentRef, ListedRef


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

    def realized_weights(self) -> dict[InstrumentRef, float]:
        """Signed realized weight (fraction of NAV) per covered :class:`InstrumentRef`.

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
        instr_to_figi: Mapping[str, InstrumentRef],
    ) -> None:
        self._portfolio = portfolio
        self._cache = cache
        self._base = base_currency
        self._instr_to_figi = instr_to_figi

    def nav(self) -> float:
        total = 0.0
        for account in self._cache.accounts():
            equity = self._portfolio.equity(account_id=account.id)
            # A base_currency=None account reports equity per currency; convert
            # every leg to base via the mark xrate (same-currency yields 1.0) so
            # foreign equity is counted, not dropped.
            for money in (equity or {}).values():
                in_base = self._in_base(money)
                if in_base is not None:
                    total += in_base
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

    def realized_weights(self) -> dict[InstrumentRef, float]:
        nav = self.nav()
        if nav <= 0:
            return {}
        weights: dict[InstrumentRef, float] = {}
        for position in self._cache.positions_open():
            ref = self._instr_to_figi.get(position.instrument_id.value)
            if ref is None:
                continue  # holding not covered by any sleeve
            if isinstance(ref, str):
                ref = ListedRef(ref)
            exposure = self._portfolio.net_exposure(position.instrument_id)
            if exposure is None:
                continue  # unpriced — no mark available
            signed = self._in_base(exposure)
            if signed is None:
                continue  # no FX rate to base — fail closed, do not fabricate
            if position.is_short:
                signed = -signed
            weights[ref] = weights.get(ref, 0.0) + signed / nav
        return weights

    def _in_base(self, exposure: Money) -> float | None:
        """Native exposure magnitude converted to base via the mark xrate, or
        ``None`` when no rate is available (same-currency yields 1.0)."""
        rate = self._cache.get_mark_xrate(exposure.currency, self._base)
        if rate is None or rate <= 0.0:
            return None
        return float(exposure.as_double()) * float(rate)
