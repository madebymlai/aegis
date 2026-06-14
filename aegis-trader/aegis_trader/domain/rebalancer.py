"""Pure-domain rebalancer: target weights → OrderIntent[].

Zero Nautilus.  For Slice 1 (tracer) this is the simplest form:
single-sleeve, no bands, no gates, no multi-sleeve netting, no FX/pence sizing,
no position diffing.  Each instrument with |weight·budget·NAV| > 0 becomes one
OrderIntent; side is the sign of the weight.
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide

_ZERO_GUARD = 1e-12


def rebalance(
    target_weights: pd.DataFrame,
    nav: float,
    book: BookConfig,
) -> list[OrderIntent]:
    """Convert the latest row of *target_weights* into provider-agnostic orders.

    For the tracer slice the book is always single-sleeve; the sleeve budget
    scales the weight before multiplying by NAV.
    """
    if target_weights.empty:
        return []

    if nav <= 0:
        raise ValueError(f"NAV must be positive; got {nav!r}")

    sleeve = book.sleeves[0]
    budget = sleeve.budget

    latest = target_weights.iloc[-1]
    orders: list[OrderIntent] = []

    for col in latest.index:
        w = float(latest[col])
        if abs(w) < _ZERO_GUARD:
            continue
        quantity = abs(w) * budget * nav
        side = OrderSide.BUY if w > 0 else OrderSide.SELL
        orders.append(OrderIntent(figi=Figi(str(col)), side=side, quantity=quantity))

    return orders
