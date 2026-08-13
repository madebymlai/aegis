from __future__ import annotations

from collections.abc import Sequence

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument

from aegis_data.bar_type import mic_canonical_instrument_id
from aegis_data.roll import DatedContract
from aegis_data.storage import Catalog


def catalog_definitions(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
) -> dict[InstrumentId, Instrument]:
    """Read definitions through the one MIC-canonicalized storage-key rule."""
    by_storage_key = {
        mic_canonical_instrument_id(instrument_id): instrument_id
        for instrument_id in instrument_ids
    }
    found = catalog.definitions(tuple(by_storage_key))
    return {
        by_storage_key[instrument.id]: instrument
        for instrument in found
        if instrument.id in by_storage_key
    }


def continuous_root_legs(catalog: Catalog, root: str) -> tuple[DatedContract, ...]:
    """List a root's expiry-ordered dated legs from Catalog definitions."""
    legs = [
        DatedContract(
            symbol=instrument.id.value,
            last_trade=instrument.expiration_utc.date(),
        )
        for instrument in catalog.futures_for_root(root)
    ]
    return tuple(sorted(legs, key=lambda leg: leg.last_trade))


def continuous_instrument_legs(
    catalog: Catalog,
    instrument_id: InstrumentId,
) -> tuple[DatedContract, ...]:
    """List dated legs for the root carried by an instrument identifier."""
    root, _separator, _venue = instrument_id.value.rpartition(".")
    return continuous_root_legs(catalog, root)


__all__ = [
    "catalog_definitions",
    "continuous_instrument_legs",
    "continuous_root_legs",
]
