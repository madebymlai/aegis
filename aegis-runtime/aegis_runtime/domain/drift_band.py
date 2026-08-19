"""Shared no-trade drift-band gate for live and research parity."""

from __future__ import annotations

import math

import msgspec
from nautilus_trader.common.config import NautilusConfig

_BOUNDARY_TOLERANCE = 1e-12


def gate(
    realized: float,
    target: float,
    up: float,
    down: float,
    destination_fraction: float = 1.0,
) -> float:
    """Resolve the held weight after applying a directional no-trade band.

    Inside the band the realized weight holds. On a breach the trade stops at
    the destination: a linear interpolation between the breached band edge
    (``destination_fraction=0.0``, the proportional-cost optimum) and the
    target (``1.0``, the fixed-fee optimum) — always inside the band, so each
    breach pays for exactly one corrective trade.
    """
    delta = target - realized
    if down > 0.0 and delta > 0.0 and delta <= down + _BOUNDARY_TOLERANCE:
        return realized
    if up > 0.0 and delta < 0.0 and -delta <= up + _BOUNDARY_TOLERANCE:
        return realized
    if delta > 0.0:
        return target - (1.0 - destination_fraction) * down
    if delta < 0.0:
        return target + (1.0 - destination_fraction) * up
    return target


class DriftBand(NautilusConfig, frozen=True, omit_defaults=True):
    """Validated directional no-trade band widths and rebalance destination."""

    up: float
    down: float
    destination_fraction: float = 1.0

    def __post_init__(self) -> None:
        up = float(self.up)
        down = float(self.down)
        destination_fraction = float(self.destination_fraction)
        if not math.isfinite(up) or up < 0.0:
            raise ValueError("DriftBand.up must be finite and non-negative")
        if not math.isfinite(down) or down < 0.0:
            raise ValueError("DriftBand.down must be finite and non-negative")
        if (
            not math.isfinite(destination_fraction)
            or not 0.0 <= destination_fraction <= 1.0
        ):
            raise ValueError("DriftBand.destination_fraction must be within [0, 1]")
        msgspec.structs.force_setattr(self, "up", up)
        msgspec.structs.force_setattr(self, "down", down)
        msgspec.structs.force_setattr(
            self, "destination_fraction", destination_fraction
        )

    @classmethod
    def symmetric(cls, width: float, destination_fraction: float = 1.0) -> DriftBand:
        return cls(up=width, down=width, destination_fraction=destination_fraction)

    def resolve(self, *, realized: float, target: float) -> float:
        return gate(realized, target, self.up, self.down, self.destination_fraction)
