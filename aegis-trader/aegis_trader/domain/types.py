"""Pure domain value types for Aegis Trader — no I/O.

Instrument identity is the native Nautilus ``InstrumentId`` from the
ExecutionBundle contract.  There is no runtime ref/symbol translation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nautilus_trader.model.identifiers import InstrumentId


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


class OrderSource(str, Enum):
    ALPHA = "ALPHA"
    ROLL = "ROLL"


@dataclass(frozen=True)
class WeightDelta:
    """A signed change in target weight for one instrument (fraction of NAV).

    The pure rebalancer emits these — netting, banding, and cap-gating all live
    in dimensionless weight space.  A separate sizing step (``sizing.size_deltas``)
    converts a WeightDelta into an :class:`OrderIntent` with a native share count.
    """

    instrument_id: InstrumentId
    delta: float  # signed weight to trade; positive = buy, negative = sell

    @property
    def side(self) -> OrderSide:
        return OrderSide.BUY if self.delta > 0 else OrderSide.SELL


@dataclass(frozen=True)
class OrderIntent:
    """A provider-agnostic, *sized* order request from the rebalance pipeline.

    Carries the native ``InstrumentId`` that the Strategy submits through
    Nautilus.
    """

    instrument_id: InstrumentId
    side: OrderSide
    quantity: float  # native share count (sized via NAV / FX / price)
    source: OrderSource = OrderSource.ALPHA
