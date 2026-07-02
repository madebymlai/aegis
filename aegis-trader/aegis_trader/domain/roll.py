"""Pure Roll lifecycle value objects."""

from __future__ import annotations

from dataclasses import dataclass

from aegis_data.rebasing import Rebasing
from nautilus_trader.model.identifiers import InstrumentId


@dataclass(frozen=True)
class RollEvent:
    """A continuous root rolled into a new price basis."""

    continuous_id: InstrumentId
    rebasing: Rebasing
