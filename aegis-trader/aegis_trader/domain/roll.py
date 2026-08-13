"""Pure Roll lifecycle value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from aegis_runtime.domain.rebasing import Rebasing
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.startup import StartupGate


@dataclass(frozen=True)
class RollEvent:
    """A continuous root rolled into a new price basis."""

    continuous_id: InstrumentId
    rebasing: Rebasing


@dataclass(frozen=True)
class SubscribeBars:
    """Subscribe to a live Bar stream read by the roll model."""

    instrument_id: InstrumentId
    timeframe: str


@dataclass(frozen=True)
class UnsubscribeBars:
    """Unsubscribe from a Bar stream no longer read by the roll model."""

    instrument_id: InstrumentId
    timeframe: str


@dataclass(frozen=True)
class RequestInstrument:
    """Load a candidate-leg instrument definition before subscribing."""

    instrument_id: InstrumentId


@dataclass(frozen=True)
class RequestBars:
    """Warm candidate-leg Bars through Nautilus's native catalog request."""

    instrument_id: InstrumentId
    timeframe: str
    start: datetime
    end: datetime
    update_catalog: bool = True


@dataclass(frozen=True)
class Halt:
    """A typed startup halt emitted by the Roll Desk."""

    gate: StartupGate
    reason: str


RollIntent: TypeAlias = (
    SubscribeBars | UnsubscribeBars | RequestInstrument | RequestBars | RollEvent | Halt
)
RollIntentBatch: TypeAlias = tuple[RollIntent, ...]
