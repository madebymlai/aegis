"""Sizing: dimensionless weight × NAV-EUR → native share quantity.

Pure — no Nautilus.  FX rates, prices, and instrument metadata are passed as
plain floats / domain types, keeping the domain core broker-free-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

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
