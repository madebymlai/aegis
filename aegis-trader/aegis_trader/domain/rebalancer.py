"""Pure-domain rebalancer: per-sleeve target weights → OrderIntent[].

Zero Nautilus.  For multi-sleeve netting (Slice 2):
- Each sleeve's target weights (latest row) are scaled by its static Sleeve Budget.
- Budget-scaled weights are netted per FIGI across all sleeves.
- A net |weight| > 0 becomes an OrderIntent; side is the sign of the net weight.
- Two sleeves sharing an instrument collapse to a single OrderIntent for the
  residual.
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide, SleeveName

_ZERO_GUARD = 1e-12


def rebalance(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    nav: float,
    book: BookConfig,
) -> list[OrderIntent]:
    """Convert per-sleeve target weights into provider-agnostic orders.

    *sleeve_targets* maps each sleeve name to its most-recent target-weight
    DataFrame (index=time, columns=FIGI).  Only sleeves listed in *book* are
    processed; sleeves missing from the dict or with empty DataFrames are
    silently skipped.

    Each sleeve's latest row is scaled by its budget, then all
    budget-scaled weights are netted per FIGI.
    """
    if nav <= 0:
        raise ValueError(f"NAV must be positive; got {nav!r}")

    # net_weight_by_figi accumulates Σ(sleeve_budget × weight) per FIGI.
    net_weight_by_figi: dict[str, float] = {}

    for sleeve in book.sleeves:
        target = sleeve_targets.get(sleeve.name)
        if target is None or target.empty:
            continue  # silently skip sleeves without data

        budget = sleeve.budget
        latest = target.iloc[-1]

        for col in latest.index:
            w = float(latest[col])
            if abs(w) < _ZERO_GUARD:
                continue
            scaled = w * budget
            figi_key = str(col)
            net_weight_by_figi[figi_key] = net_weight_by_figi.get(figi_key, 0.0) + scaled

    # Emit one OrderIntent per FIGI with non-zero net weight.
    orders: list[OrderIntent] = []
    for figi_key, net_w in net_weight_by_figi.items():
        if abs(net_w) < _ZERO_GUARD:
            continue
        quantity = abs(net_w) * nav
        side = OrderSide.BUY if net_w > 0 else OrderSide.SELL
        orders.append(OrderIntent(figi=Figi(figi_key), side=side, quantity=quantity))

    return orders
