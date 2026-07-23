"""Validated native facts from Nautilus instrument definitions."""

from __future__ import annotations

import math

from nautilus_trader.model.instruments import Instrument


def native_size_increment(instrument: Instrument) -> float:
    """Return the positive finite order-size increment authored on *instrument*."""

    increment = float(instrument.size_increment)
    if not math.isfinite(increment) or increment <= 0.0:
        raise ValueError(
            f"instrument {instrument.id} has invalid size increment {increment!r}"
        )
    return increment


def native_multiplier(instrument: Instrument) -> float:
    """Return the positive finite contract multiplier authored on *instrument*."""

    multiplier = float(instrument.multiplier)
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError(
            f"instrument {instrument.id} has invalid multiplier {multiplier!r}"
        )
    return multiplier
