"""Assemble a valid Commingled Book from its configured Execution Bundles."""

from __future__ import annotations

import logging as _logging
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from types import MappingProxyType as _MappingProxyType

from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.array_names import OHLCV_ARRAY_NAMES
from aegis_data.custom_data import (
    AVAILABILITY_BY_VALUE,
    KNOWN_CUSTOM_ARRAY_NAMES,
    VOCABULARY,
)
from aegis_runtime import DriftBand, ExecutionBundle

from aegis_trader.bundles.bands import BundleBands, InstrumentBandError
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.domain.analytics_horizon import AnalyticsHorizon, derive_horizon
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.streams import MarketStream, StreamRequirement, stream_sort_key
from aegis_trader.domain.types import SleeveName

_log = _logging.getLogger(__name__)

@_dataclass(frozen=True)
class ContinuousRootDeclaration:
    """One coherent continuous-root declaration.

    ``timeframe`` is the owning Sleeve's contract cadence: one root has one
    owning Sleeve and therefore one required stream (aegis-rd-9qkr.5) — a root
    declared at two timeframes is an incoherent declaration and fails closed.
    """

    continuous_id: InstrumentId
    adjustment_mode: ContinuousFutureAdjustmentType
    timeframe: str


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
            f"{existing.continuous_id.value}/{existing.adjustment_mode.value}"
            f"/{existing.timeframe} vs {conflicting.continuous_id.value}"
            f"/{conflicting.adjustment_mode.value}/{conflicting.timeframe}"
        )


class UndeliverableArrayError(ValueError):
    """A Sleeve declares a required array no data path can materialize.

    Without this check the Book assembles, and the Sleeve then fails every
    rebalance as a swallowed per-period compute error (aegis-rd-nar9)."""

    def __init__(self, *, sleeve: SleeveName, arrays: tuple[str, ...]) -> None:
        self.sleeve = sleeve
        self.arrays = arrays
        super().__init__(
            f"sleeve {sleeve.value!r} requires array(s) {list(arrays)} that no "
            f"data path can materialize; deliverable arrays are "
            f"{sorted((*OHLCV_ARRAY_NAMES, *VOCABULARY))}"
        )


class UnprovisionedArrayError(ValueError):
    """A Sleeve names a known custom kind with no provider wired."""

    def __init__(self, *, sleeve: SleeveName, arrays: tuple[str, ...]) -> None:
        self.sleeve = sleeve
        self.arrays = arrays
        super().__init__(
            f"sleeve {sleeve.value!r} requires known custom array(s) {list(arrays)} "
            "whose kind has no provider wired"
        )


class MissingAvailabilityArrayError(ValueError):
    """A custom value is declared without its availability signal."""

    def __init__(
        self,
        *,
        sleeve: SleeveName,
        value_array: str,
        availability_array: str,
    ) -> None:
        self.sleeve = sleeve
        self.value_array = value_array
        self.availability_array = availability_array
        super().__init__(
            f"sleeve {sleeve.value!r} declares value array {value_array!r} without "
            f"required availability array {availability_array!r}"
        )


@_dataclass(frozen=True)
class AssembledBook:
    config: BookConfig
    sleeves: _Mapping[SleeveName, ExecutionBundle]
    loadable_instrument_ids: tuple[InstrumentId, ...]
    requires_margin: bool
    bands: BundleBands
    continuous_declarations: _Mapping[str, ContinuousRootDeclaration]
    # Each root's deepest consumer history need, in its own stream's bars.
    continuous_history_bars: _Mapping[str, int]
    sleeve_streams: _Mapping[SleeveName, tuple[MarketStream, ...]]
    required_streams: tuple[StreamRequirement, ...]
    # Derived from the roster's declared cadences — the Book's one bucketing
    # and annualization fact (aegis-rd-cy7l).
    analytics_horizon: AnalyticsHorizon


def assemble_book(book_config: BookConfig, registry: BundleRegistryPort) -> AssembledBook:
    """Resolve every Sleeve and prove all structural Commingled Book invariants."""
    sleeves = _load_sleeves(book_config, registry)
    _validate_required_arrays(sleeves)
    continuous_declarations = _continuous_declarations(sleeves)
    analytics_horizon = derive_horizon(
        tuple(bundle.contract.timeframe for bundle in sleeves.values())
    )
    _log.info(
        "Analytics horizon: %s, derived from the roster", analytics_horizon.describe()
    )

    return AssembledBook(
        config=book_config,
        sleeves=sleeves,
        loadable_instrument_ids=_loadable_instrument_ids(sleeves),
        requires_margin=any(
            bundle.direction in {"both", "shortonly"}
            for bundle in sleeves.values()
        ),
        bands=_assemble_bands(sleeves),
        continuous_declarations=_MappingProxyType(
            dict(sorted(continuous_declarations.items()))
        ),
        continuous_history_bars=_continuous_history_bars(sleeves),
        sleeve_streams=_sleeve_streams(sleeves),
        required_streams=_required_streams(sleeves),
        analytics_horizon=analytics_horizon,
    )


def _validate_required_arrays(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> None:
    for sleeve_name, bundle in sleeves.items():
        required = set(bundle.contract.required_arrays)
        known = set(OHLCV_ARRAY_NAMES) | KNOWN_CUSTOM_ARRAY_NAMES
        undeliverable = tuple(
            sorted(required - known)
        )
        if undeliverable:
            raise UndeliverableArrayError(sleeve=sleeve_name, arrays=undeliverable)
        unprovisioned = tuple(sorted(required & (KNOWN_CUSTOM_ARRAY_NAMES - VOCABULARY)))
        if unprovisioned:
            raise UnprovisionedArrayError(sleeve=sleeve_name, arrays=unprovisioned)
        for value_array, availability_array in AVAILABILITY_BY_VALUE.items():
            if value_array in required and availability_array not in required:
                raise MissingAvailabilityArrayError(
                    sleeve=sleeve_name,
                    value_array=value_array,
                    availability_array=availability_array,
                )


def _contract_history_bars(bundle: ExecutionBundle) -> int:
    """The bar count a bundle's compute needs: its lookback plus the decision bar."""
    return bundle.contract.lookback_bars + 1


def _continuous_history_bars(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> _Mapping[str, int]:
    history: dict[str, int] = {}
    for bundle in sleeves.values():
        for root in bundle.contract.futures:
            history[root] = max(history.get(root, 0), _contract_history_bars(bundle))
    return _MappingProxyType(dict(sorted(history.items())))


def _sleeve_streams(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> _Mapping[SleeveName, tuple[MarketStream, ...]]:
    return _MappingProxyType(
        {
            sleeve_name: tuple(
                sorted(
                    (
                        MarketStream(instrument_id, bundle.contract.timeframe)
                        for instrument_id in bundle.contract.loadable_instrument_ids
                    ),
                    key=stream_sort_key,
                )
            )
            for sleeve_name, bundle in sleeves.items()
        }
    )


def _required_streams(
    sleeves: _Mapping[SleeveName, ExecutionBundle],
) -> tuple[StreamRequirement, ...]:
    history_bars: dict[MarketStream, int] = {}
    consumers: dict[MarketStream, dict[SleeveName, None]] = {}
    for sleeve_name, bundle in sleeves.items():
        needed = _contract_history_bars(bundle)
        for instrument_id in bundle.contract.loadable_instrument_ids:
            stream = MarketStream(instrument_id, bundle.contract.timeframe)
            history_bars[stream] = max(history_bars.get(stream, 0), needed)
            consumers.setdefault(stream, {})[sleeve_name] = None
    return tuple(
        StreamRequirement(
            stream=stream,
            history_bars=history_bars[stream],
            consumers=tuple(sorted(consumers[stream], key=lambda name: name.value)),
        )
        for stream in sorted(history_bars, key=stream_sort_key)
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
                timeframe=contract.timeframe,
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
    "UndeliverableArrayError",
    "assemble_book",
]
