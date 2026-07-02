"""Continuous-root identity resolver for catalog-backed roots."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId, Symbol

from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.catalog_contracts import catalog_contract_calendar
from aegis_data.roll import DatedContract


class ContinuousCatalogError(Exception):
    """Base class for continuous-root identity resolver failures."""


class ContinuousRootLegsNotFoundError(ContinuousCatalogError):
    """The catalog has no dated legs for a requested continuous root."""


class ContinuousRootVenueMismatchError(ContinuousCatalogError):
    """A continuous root's dated legs span more than one venue."""


def continuous_instrument_ids(
    port: CatalogBackedDataPort,
    roots: Sequence[str],
    *,
    start: str,
    end: str,
) -> tuple[InstrumentId, ...]:
    """Resolve bare continuous-future roots to synthetic continuous InstrumentIds."""
    catalog = port.catalog
    return tuple(
        continuous_instrument_id(root, continuous_root_legs(catalog, root, start, end))
        for root in roots
    )


def continuous_root_legs(
    catalog: object, root: str, start: str, end: str
) -> Sequence[DatedContract]:
    """The root's dated legs, failing loud when the catalog has no cycle."""
    legs = catalog_contract_calendar(catalog)(
        root, pd.Timestamp(start).date(), pd.Timestamp(end).date()
    )
    if not legs:
        raise ContinuousRootLegsNotFoundError(
            f"no dated legs in the catalog for continuous-future root {root!r}"
        )
    return legs


def continuous_instrument_id(root: str, legs: Sequence[DatedContract]) -> InstrumentId:
    """The synthetic continuous-root id, with venue validated from the dated legs."""
    venues = {InstrumentId.from_str(leg.symbol).venue for leg in legs}
    if len(venues) != 1:
        raise ContinuousRootVenueMismatchError(
            f"continuous-future root {root!r} legs span multiple venues "
            f"{sorted(venue.value for venue in venues)}; expected one"
        )
    return InstrumentId(Symbol(root), next(iter(venues)))


__all__ = [
    "ContinuousCatalogError",
    "ContinuousRootLegsNotFoundError",
    "ContinuousRootVenueMismatchError",
    "continuous_instrument_id",
    "continuous_instrument_ids",
    "continuous_root_legs",
]
