"""Assemble a valid Commingled Book from its configured Execution Bundles."""

from __future__ import annotations

from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from types import MappingProxyType as _MappingProxyType

from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import DriftBand, ExecutionBundle

from aegis_trader.bundles.bands import BundleBands, InstrumentBandError
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.book_timeframe import _resolve_book_timeframe
from aegis_trader.domain.types import SleeveName

@_dataclass(frozen=True)
class ContinuousRootDeclaration:
    """One coherent continuous-root declaration."""

    continuous_id: InstrumentId
    adjustment_mode: ContinuousFutureAdjustmentType


class ContinuousDeclarationConflictError(ValueError):
    """Two Sleeves declare one root with incompatible facts."""

    def __init__(
        self,
        *,
        root: str,
        sleeves: tuple[SleeveName, ...],
        existing: ContinuousRootDeclaration,
        conflicting: ContinuousRootDeclaration,
    ) -> None:
        self.root = root
        self.sleeves = sleeves
        self.existing = existing
        self.conflicting = conflicting
        super().__init__(
            f"continuous root {root!r} is declared incoherently across sleeves "
            f"{[str(name) for name in sleeves]}: "
            f"{existing.continuous_id.value}/{existing.adjustment_mode.value} "
            f"vs {conflicting.continuous_id.value}/{conflicting.adjustment_mode.value}"
        )


@_dataclass(frozen=True)
class AssembledBook:
    config: BookConfig
    sleeves: _Mapping[SleeveName, ExecutionBundle]
    timeframe: str
    loadable_instrument_ids: tuple[InstrumentId, ...]
    required_bar_window: int
    requires_margin: bool
    bands: BundleBands
    continuous_declarations: _Mapping[str, ContinuousRootDeclaration]


def assemble_book(book_config: BookConfig, registry: BundleRegistryPort) -> AssembledBook:
    """Resolve every Sleeve and prove all structural Commingled Book invariants."""
    sleeves = _load_sleeves(book_config, registry)
    continuous_declarations = _continuous_declarations(sleeves)

    return AssembledBook(
        config=book_config,
        sleeves=sleeves,
        timeframe=_resolve_book_timeframe(
            bundle.contract.timeframe for bundle in sleeves.values()
        ),
        loadable_instrument_ids=_loadable_instrument_ids(sleeves),
        required_bar_window=max(
            bundle.contract.lookback_bars for bundle in sleeves.values()
        )
        + 1,
        requires_margin=any(
            bundle.direction in {"both", "shortonly"}
            for bundle in sleeves.values()
        ),
        bands=_assemble_bands(sleeves),
        continuous_declarations=_MappingProxyType(
            dict(sorted(continuous_declarations.items()))
        ),
    )


def _continuous_declarations(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> dict[str, ContinuousRootDeclaration]:
    declarations: dict[str, ContinuousRootDeclaration] = {}
    declaring_sleeves: dict[str, list[SleeveName]] = {}
    for sleeve_name, bundle in sleeves.items():
        contract = bundle.contract
        continuous_by_root = {
            instrument_id.symbol.value: instrument_id
            for instrument_id in contract.continuous_instrument_ids
        }
        mode = contract.adjustment_mode
        for root in contract.futures:
            assert mode is not None
            declaration = ContinuousRootDeclaration(
                continuous_id=continuous_by_root[root],
                adjustment_mode=mode,
            )
            existing = declarations.setdefault(root, declaration)
            declaring_sleeves.setdefault(root, []).append(sleeve_name)
            if existing != declaration:
                raise ContinuousDeclarationConflictError(
                    root=root,
                    sleeves=tuple(declaring_sleeves[root]),
                    existing=existing,
                    conflicting=declaration,
                )
    return declarations


def _load_sleeves(
    book: BookConfig,
    registry: BundleRegistryPort,
) -> _Mapping[SleeveName, ExecutionBundle]:
    loaded = {
        sleeve.name: registry.load(sleeve.wheel_filename) for sleeve in book.sleeves
    }
    return _MappingProxyType(
        dict(sorted(loaded.items(), key=lambda item: item[0].value))
    )


def _loadable_instrument_ids(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> tuple[InstrumentId, ...]:
    unique: dict[str, InstrumentId] = {}
    for bundle in sleeves.values():
        for instrument_id in bundle.contract.loadable_instrument_ids:
            unique.setdefault(instrument_id.value, instrument_id)
    return tuple(sorted(unique.values(), key=lambda instrument_id: instrument_id.value))


def _assemble_bands(
    bundles: _Mapping[SleeveName, ExecutionBundle],
) -> BundleBands:
    owners: dict[InstrumentId, SleeveName] = {}
    bands: dict[InstrumentId, DriftBand] = {}
    for sleeve_name, bundle in bundles.items():
        for instrument_id, band in sorted(
            bundle.instrument_bands.items(), key=lambda item: item[0].value
        ):
            owner = owners.get(instrument_id)
            if owner is not None:
                raise InstrumentBandError(
                    instrument_id=instrument_id,
                    sleeves=(owner, sleeve_name),
                )
            owners[instrument_id] = sleeve_name
            bands[instrument_id] = band
    return BundleBands(
        bands=_MappingProxyType(bands),
        owner_by_instrument=_MappingProxyType(owners),
    )


__all__ = [
    "AssembledBook",
    "ContinuousDeclarationConflictError",
    "ContinuousRootDeclaration",
    "assemble_book",
]
