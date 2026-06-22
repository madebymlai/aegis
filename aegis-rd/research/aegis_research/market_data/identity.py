"""The single home for turning config/panel identity into Nautilus InstrumentIds."""

from __future__ import annotations

from collections.abc import Iterable

from nautilus_trader.model.identifiers import InstrumentId

__all__ = ["as_instrument_id", "instrument_ids"]


def instrument_ids(values: Iterable[str]) -> tuple[InstrumentId, ...]:
    """Parse native InstrumentId strings (config order preserved)."""
    return tuple(InstrumentId.from_str(value) for value in values)


def as_instrument_id(value: object) -> InstrumentId:
    """Coerce a panel column key (already an InstrumentId, or its string) to an InstrumentId."""
    if isinstance(value, InstrumentId):
        return value
    return InstrumentId.from_str(str(value))
