"""Load a Book Config's sleeves and union their loadable instrument ids.

Both the offline backtest runner and the live trader node start the same way:
resolve each Book Config sleeve to its installed :class:`ExecutionBundle` and take
the union of the bundles' ``DataContract.loadable_instrument_ids`` — the declared
tradeable natives plus the data-only FX ``exchange:`` conversion legs (e.g.
``EUR/USD.IDEALPRO``).  Nothing is constructed or currency-derived: the live
node feeds the union to IBKR's InstrumentProvider ``load_ids``; the backtest loads
the same set from the catalog.  This is the one place that mapping lives.
"""

from __future__ import annotations

from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import ExecutionBundle

from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName

SleeveBundles = tuple[tuple[SleeveName, ExecutionBundle], ...]


def load_book_sleeves(book: BookConfig, registry: BundleRegistryPort) -> SleeveBundles:
    """Resolve each sleeve in *book* to its installed ExecutionBundle, in order."""
    return tuple(
        (sleeve.name, registry.load(sleeve.wheel_filename)) for sleeve in book.sleeves
    )


def union_loadable_instrument_ids(sleeves: SleeveBundles) -> tuple[InstrumentId, ...]:
    """The sorted union of the sleeves' loadable ``InstrumentId`` values: the
    declared natives plus the data-only FX ``exchange:`` conversion legs.

    Continuous-future synthetic ids are excluded — their legs load dynamically via the
    chain, never as static native columns (see ``DataContract.native_instrument_ids``).
    """
    unique: dict[str, InstrumentId] = {}
    for _name, bundle in sleeves:
        for instrument_id in bundle.contract.loadable_instrument_ids:
            unique.setdefault(instrument_id.value, instrument_id)
    return tuple(sorted(unique.values(), key=lambda instrument_id: instrument_id.value))
