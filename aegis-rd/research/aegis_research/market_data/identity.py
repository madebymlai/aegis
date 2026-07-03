"""The single home for turning config/panel identity into Nautilus InstrumentIds."""

from __future__ import annotations

from collections.abc import Iterable

from aegis_data.catalog import catalog_data_port
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import RunConfig

__all__ = ["as_instrument_id", "instrument_ids", "resolved_instruments"]


def instrument_ids(values: Iterable[str]) -> tuple[InstrumentId, ...]:
    """Parse native InstrumentId strings (config order preserved)."""
    return tuple(InstrumentId.from_str(value) for value in values)


def as_instrument_id(value: object) -> InstrumentId:
    """Coerce a panel column key (already an InstrumentId, or its string) to an InstrumentId."""
    if isinstance(value, InstrumentId):
        return value
    return InstrumentId.from_str(str(value))


def resolved_instruments(config: RunConfig) -> tuple[tuple[InstrumentId, str | None], ...]:
    """Each tradeable as ``(full InstrumentId, its bare data.futures root or None)``.

    The single source of the native→future ordering and the id↔root pairing: callers
    derive both the contract instrument ids and the per-instrument band map from this,
    so no second site re-zips resolved ids against ``data.futures``. The continuous-id
    venue is catalog-authoritative; a run with no futures never opens the catalog.
    """
    data = config.data
    native = tuple((InstrumentId.from_str(value), None) for value in data.instruments)
    if not data.futures:
        return native
    port = catalog_data_port(data.path)
    future_ids = tuple(
        port.resolve_continuous(root).instrument_id for root in data.futures
    )
    return (*native, *tuple(zip(future_ids, data.futures, strict=True)))
