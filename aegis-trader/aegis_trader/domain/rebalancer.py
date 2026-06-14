"""Pure-domain rebalancer: per-sleeve target weights → OrderIntent[].

Zero Nautilus.  For multi-sleeve netting (Slice 2):
- Each sleeve's target weights (latest row) are scaled by its static Sleeve Budget.
- Budget-scaled weights are netted per FIGI across all sleeves.
- A net |weight| > 0 becomes an OrderIntent; side is the sign of the net weight.
- Two sleeves sharing an instrument collapse to a single OrderIntent for the
  residual.

For sizing (Slice 5):
- EUR notional = |net weight| × NAV-in-EUR → native share quantity via FX,
  GBp pence factor, and increment rounding.
- Sub-increment quantities are silently dropped (no OrderIntent emitted).
"""

from __future__ import annotations

import pandas as pd

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.sizing import InstrumentSizing, size_order
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide, SleeveName

_ZERO_GUARD = 1e-12


def rebalance(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    nav: float,
    book: BookConfig,
    *,
    instrument_metas: dict[str, InstrumentSizing] | None = None,
    fx_rates: dict[str, float] | None = None,
    prices: dict[str, float] | None = None,
) -> list[OrderIntent]:
    """Convert per-sleeve target weights into provider-agnostic orders.

    *sleeve_targets* maps each sleeve name to its most-recent target-weight
    DataFrame (index=time, columns=FIGI).  Only sleeves listed in *book* are
    processed; sleeves missing from the dict or with empty DataFrames are
    silently skipped.

    Each sleeve's latest row is scaled by its budget, then all
    budget-scaled weights are netted per FIGI.

    *instrument_metas* maps FIGI → InstrumentSizing (currency, size_increment).
    *fx_rates* maps currency → units of that currency per 1 EUR.
    *prices* maps FIGI → latest close price in the instrument's native currency.

    When sizing params are supplied the rebalancer converts the EUR-notional
    target into a native share quantity rounded to the instrument's size
    increment, dropping sub-increment orders silently.  When omitted the
    quantity in the OrderIntent is the raw EUR notional (backward-compatible
    with Slice 1–2 callers).
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
        notional_eur = abs(net_w) * nav
        side = OrderSide.BUY if net_w > 0 else OrderSide.SELL

        # Slice 5: size the EUR notional into native share quantity.
        quantity = _size_if_configured(
            notional_eur=notional_eur,
            figi_key=figi_key,
            instrument_metas=instrument_metas,
            fx_rates=fx_rates,
            prices=prices,
        )
        if quantity is None:
            continue  # sub-increment → no order

        orders.append(OrderIntent(figi=Figi(figi_key), side=side, quantity=quantity))

    return orders


def _size_if_configured(
    notional_eur: float,
    figi_key: str,
    instrument_metas: dict[str, InstrumentSizing] | None,
    fx_rates: dict[str, float] | None,
    prices: dict[str, float] | None,
) -> float | None:
    """Size to native quantity when all sizing params are available; otherwise
    return the raw EUR notional (backward-compatible with pre-Slice 5 callers)."""
    if instrument_metas is None or fx_rates is None or prices is None:
        return notional_eur  # backward-compatible: raw EUR notional

    meta = instrument_metas.get(figi_key)
    price = prices.get(figi_key)
    if meta is None or price is None:
        return notional_eur  # unknown instrument → pass through raw notional

    currency = meta.currency
    fx_rate = fx_rates.get(currency)
    if fx_rate is None:
        return notional_eur  # missing FX rate → pass through raw notional

    return size_order(notional_eur, price, fx_rate, meta)
