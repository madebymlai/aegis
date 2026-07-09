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

from dataclasses import dataclass

from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import ExecutionBundle

from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName

SleeveBundles = tuple[tuple[SleeveName, ExecutionBundle], ...]


@dataclass(frozen=True)
class ContinuousRootDeclaration:
    """One coherent continuous-root declaration: the synthetic id the root
    materialises as, and the re-basing algebra its locked Run recorded."""

    continuous_id: InstrumentId
    adjustment_mode: ContinuousFutureAdjustmentType


class ContinuousDeclarationConflictError(ValueError):
    """Two Sleeves declare the same root with a different id or adjustment mode."""


def union_continuous_declarations(
    sleeves: SleeveBundles,
) -> dict[str, ContinuousRootDeclaration]:
    """Project every futures root from every loaded DataContract into one
    declaration per bare root.

    An identical declaration repeated by multiple Sleeves collapses to one
    entry; a Commingled Book may use different modes for *different* roots, but
    the same root disagreeing on continuous id or adjustment mode is a
    startup-stopping conflict.
    """
    declarations: dict[str, ContinuousRootDeclaration] = {}
    declaring_sleeves: dict[str, list[SleeveName]] = {}
    for sleeve_name, bundle in sleeves:
        contract = bundle.contract
        continuous_by_root = {
            instrument_id.symbol.value: instrument_id
            for instrument_id in contract.continuous_instrument_ids
        }
        mode = contract.adjustment_mode
        for root in contract.futures:
            if mode is None:  # unreachable: DataContract enforces mode-iff-futures
                raise ContinuousDeclarationConflictError(
                    f"continuous root {root!r} declared without an adjustment mode"
                )
            declaration = ContinuousRootDeclaration(
                continuous_id=continuous_by_root[root],
                adjustment_mode=mode,
            )
            existing = declarations.setdefault(root, declaration)
            declaring_sleeves.setdefault(root, []).append(sleeve_name)
            if existing != declaration:
                raise ContinuousDeclarationConflictError(
                    f"continuous root {root!r} is declared incoherently across "
                    f"sleeves {[str(name) for name in declaring_sleeves[root]]}: "
                    f"{existing.continuous_id.value}/{existing.adjustment_mode.value} "
                    f"vs {declaration.continuous_id.value}/"
                    f"{declaration.adjustment_mode.value}"
                )
    return declarations


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
