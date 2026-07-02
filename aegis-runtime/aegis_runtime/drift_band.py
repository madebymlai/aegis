"""Shared no-trade drift-band gate for live and research parity."""

from __future__ import annotations

import math
from dataclasses import dataclass

_BOUNDARY_TOLERANCE = 1e-12


def gate(realized: float, target: float, up: float, down: float) -> float:
    """Resolve the held weight after applying a directional no-trade band."""
    delta = target - realized
    if down > 0.0 and delta > 0.0 and delta <= down + _BOUNDARY_TOLERANCE:
        return realized
    if up > 0.0 and delta < 0.0 and -delta <= up + _BOUNDARY_TOLERANCE:
        return realized
    return target


@dataclass(frozen=True)
class DriftBand:
    """Validated directional no-trade band widths."""

    up: float
    down: float

    def __post_init__(self) -> None:
        up = float(self.up)
        down = float(self.down)
        if not math.isfinite(up) or up < 0.0:
            raise ValueError("DriftBand.up must be finite and non-negative")
        if not math.isfinite(down) or down < 0.0:
            raise ValueError("DriftBand.down must be finite and non-negative")
        object.__setattr__(self, "up", up)
        object.__setattr__(self, "down", down)

    @classmethod
    def symmetric(cls, width: float) -> DriftBand:
        return cls(up=width, down=width)

    def resolve(self, *, realized: float, target: float) -> float:
        return gate(realized, target, self.up, self.down)
