"""The single home for turning config/panel identity into Nautilus InstrumentIds."""

from __future__ import annotations

from collections.abc import Iterable

from aegis_data.catalog import catalog_data_port
from aegis_data.continuous_catalog import continuous_instrument_ids
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
    venue is catalog-authoritative, so resolving futures opens the catalog over the run
    window; a run with no futures needs neither.
    """
    data = config.data
    native = tuple((InstrumentId.from_str(value), None) for value in data.instruments)
    if not data.futures:
        return native
    future_ids = continuous_instrument_ids(
        catalog_data_port(data.path),
        data.futures,
        start=_required_catalog_window_edge(data.start, "start"),
        end=_required_catalog_window_edge(data.end, "end"),
    )
    return (*native, *tuple(zip(future_ids, data.futures, strict=True)))


def _required_catalog_window_edge(value: str | None, label: str) -> str:
    if value is None:
        raise ValueError(f"data.{label} is required to resolve continuous-future roots")
    return value
