"""Pure domain value types for Aegis Trader — no Nautilus, no I/O.

All instrument identifiers are canonical InstrumentRefs from the DataContract,
so the domain core never depends on venue-specific instrument resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from aegis_runtime import InstrumentRef


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
class ResolvedContractId:
    """Venue-native contract id as a domain string, not a Nautilus type."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError(f"ResolvedContractId must be a non-empty string; got {self.value!r}")


@dataclass(frozen=True)
class WeightDelta:
    """A signed change in target weight for one InstrumentRef (fraction of NAV).

    The pure rebalancer emits these — netting, banding, and cap-gating all live
    in dimensionless weight space.  A separate sizing step (``sizing.size_deltas``)
    converts a WeightDelta into an :class:`OrderIntent` with a native share count.
    """

    ref: InstrumentRef
    delta: float  # signed weight to trade; positive = buy, negative = sell

    @property
    def side(self) -> OrderSide:
        return OrderSide.BUY if self.delta > 0 else OrderSide.SELL


@dataclass(frozen=True)
class OrderIntent:
    """A provider-agnostic, *sized* order request from the rebalance pipeline.

    Carries canonical identifiers; the Strategy asks the pipeline for the
    current venue-specific instrument before submitting through Nautilus.
    """

    ref: InstrumentRef
    side: OrderSide
    quantity: float  # native share count (sized via NAV / FX / price)
    source: OrderSource = OrderSource.ALPHA
    resolved_contract_id: ResolvedContractId | None = None
