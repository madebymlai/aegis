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
    """Subscribe to live bars for a front leg."""

    instrument_id: InstrumentId
    timeframe: str


@dataclass(frozen=True)
class UnsubscribeBars:
    """Unsubscribe from live bars for an old front leg."""

    instrument_id: InstrumentId
    timeframe: str


@dataclass(frozen=True)
class RequestInstrument:
    """Load a front-leg instrument definition before subscribing."""

    instrument_id: InstrumentId


@dataclass(frozen=True)
class RequestBars:
    """Warm front-leg bars through Nautilus's native catalog request."""

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
