"""Pure domain value types for Aegis Trader — no Nautilus, no I/O.

All identifiers are canonical (FIGI from the DataContract, SleeveName from the
Book Config) so the domain core never depends on venue-specific instrument
resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Figi:
    """A Financial Instrument Global Identifier (FIGI) — 12-char alphanumeric."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not isinstance(self.value, str):
            raise ValueError(f"FIGI must be a non-empty string; got {self.value!r}")


@dataclass(frozen=True)
class SleeveName:
    """A sleeve identifier as named in the Book Config (e.g. "trend_lse")."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not isinstance(self.value, str):
            raise ValueError(f"SleeveName must be a non-empty string; got {self.value!r}")


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class WeightDelta:
    """A signed change in target weight for one instrument (fraction of NAV).

    The pure rebalancer emits these — netting, banding, and cap-gating all live
    in dimensionless weight space.  A separate sizing step (``sizing.size_deltas``)
    converts a WeightDelta into an :class:`OrderIntent` with a native share count.
    """

    figi: Figi
    delta: float  # signed weight to trade; positive = buy, negative = sell

    @property
    def side(self) -> OrderSide:
        return OrderSide.BUY if self.delta > 0 else OrderSide.SELL


@dataclass(frozen=True)
class OrderIntent:
    """A provider-agnostic, *sized* order request from the rebalance pipeline.

    Carries only canonical identifiers; the execution port resolves the FIGI to
    a venue-specific instrument before submitting.
    """

    figi: Figi
    side: OrderSide
    quantity: float  # native share count (sized via NAV / FX / price)
