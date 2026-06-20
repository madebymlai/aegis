"""Sizing: dimensionless weight × NAV-EUR → native share quantity.

Pure — no Nautilus.  FX rates, prices, and instrument metadata are passed as
plain floats / domain types, keeping the domain core broker-free-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from aegis_runtime import InstrumentRef

from aegis_trader.domain.types import OrderIntent, WeightDelta

_PENCE_FACTOR = 100.0
_GBP_CURRENCY = "GBp"


@dataclass(frozen=True)
class InstrumentSizing:
    """Per-instrument metadata needed for sizing — pure domain type."""

    currency: str
    size_increment: float


def size_order(
    notional_eur: float,
    price: float,
    fx_rate: float,
    instrument: InstrumentSizing,
) -> float | None:
    """Convert EUR notional to native share quantity.

    *notional_eur* is the absolute value of the budget-scaled net weight
    times NAV-in-EUR — the target exposure in euros.

    *price* is the instrument's latest close price in its native currency.

    *fx_rate* is units of the instrument's **major** quote currency per
    1 EUR — e.g. 0.85 for a GBP instrument (1 EUR = 0.85 GBP), or 1.10 for
    a USD instrument.  For a GBp (London pence) instrument the rate must be
    **GBP/EUR**, not GBp/EUR — the pence factor of 100× is applied inside this
    function, so the GBp price and GBP/EUR rate compose to the correct
    native notional.

    Returns ``None`` when the rounded quantity is zero (sub-increment).

    Raises nothing — invalid inputs return ``None`` so the caller can skip the
    order cleanly.
    """
    if notional_eur <= 0.0 or price <= 0.0 or fx_rate <= 0.0:
        return None

    notional_native = notional_eur * fx_rate

    if instrument.currency == _GBP_CURRENCY:
        notional_native *= _PENCE_FACTOR

    raw_quantity = notional_native / price
    rounded = _round_to_increment(raw_quantity, instrument.size_increment)

    if rounded <= 0.0:
        return None
    return rounded


def _round_to_increment(value: float, increment: float) -> float:
    """Round *value* to the nearest multiple of *increment*."""
    if increment <= 0.0:
        return value
    return round(value / increment) * increment


def size_deltas(
    deltas: tuple[WeightDelta, ...],
    nav: float,
    *,
    instrument_metas: Mapping[InstrumentRef, InstrumentSizing],
    fx_rates: Mapping[str, float],
    prices: Mapping[InstrumentRef, float],
) -> tuple[OrderIntent, ...]:
    """Convert signed weight deltas into sized, provider-agnostic orders.

    The sizing half of the rebalance pipeline: the pure (weight-space)
    rebalancer decides *what* to trade; this decides *how much* in native
    shares.  ``nav`` is the account NAV in base currency (EUR).

    Each delta's EUR notional (``|delta| · nav``) is converted to a native share
    count via the instrument's currency/FX/pence factor and rounded to its size
    increment.  A delta is silently dropped when its instrument metadata, price,
    or FX rate is unavailable, or when the rounded quantity is sub-increment —
    there is no order to place.
    """
    if nav <= 0:
        raise ValueError(f"NAV must be positive; got {nav!r}")

    orders: list[OrderIntent] = []
    for d in deltas:
        meta = instrument_metas.get(d.ref)
        price = prices.get(d.ref)
        if meta is None or price is None:
            continue
        fx_rate = fx_rates.get(meta.currency)
        if fx_rate is None:
            continue
        quantity = size_order(abs(d.delta) * nav, price, fx_rate, meta)
        if quantity is None:
            continue  # sub-increment -> no order
        orders.append(OrderIntent(ref=d.ref, side=d.side, quantity=quantity))
    return tuple(orders)

