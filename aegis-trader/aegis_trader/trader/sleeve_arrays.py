"""Complete array panels for one Sleeve behind a small interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd
from aegis_data.array_names import is_bar_derived_array
from aegis_data.custom_data import (
    CustomDataProviderMap,
    arrays as project_custom_arrays,
    ensure_arrays,
)
from aegis_data.storage import Catalog
from aegis_data.custom_kinds import CustomDataRegistry
from aegis_runtime import DataContract
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.data.market_data import MarketBar


class EmptySleeveArrayGridError(ValueError):
    """A Sleeve array grid cannot be derived without any bars."""


class CustomArrayCatalogNotConfiguredError(RuntimeError):
    """Catalog-backed arrays were requested from a bar-only assembler."""


class SleeveArrayShapeError(ValueError):
    """A projected panel does not match its declared Sleeve grid."""


class InvalidArrayIntervalError(ValueError):
    """An array interval ends before it starts."""


@dataclass(frozen=True)
class ArrayNeed:
    """Required array names and instruments over one closed interval."""

    names: tuple[str, ...]
    instrument_ids: tuple[InstrumentId, ...]
    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise InvalidArrayIntervalError("array start must not be after end")

    @classmethod
    def from_contract(
        cls,
        contract: DataContract,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ArrayNeed:
        """Build the declared need for an explicit startup window."""
        return cls(
            names=tuple(contract.required_arrays),
            instrument_ids=tuple(contract.instrument_ids),
            start=start,
            end=end,
        )


@dataclass(frozen=True)
class SleeveArrayGrid:
    """One Sleeve's declared arrays on the exact union of its supplied bars."""

    need: ArrayNeed
    bars: Mapping[InstrumentId, Sequence[MarketBar]]
    index: pd.DatetimeIndex

    @classmethod
    def from_bars(
        cls,
        contract: DataContract,
        bars: Mapping[InstrumentId, Sequence[MarketBar]],
    ) -> SleeveArrayGrid:
        """Derive the exact projection grid from the caller's qualified bars."""
        index = pd.DatetimeIndex(
            sorted(
                {
                    bar.ts_event
                    for instrument_bars in bars.values()
                    for bar in instrument_bars
                }
            )
        )
        if len(index) == 0:
            raise EmptySleeveArrayGridError("cannot build Sleeve arrays without bars")
        need = ArrayNeed.from_contract(
            contract,
            start=pd.Timestamp(index[0]),
            end=pd.Timestamp(index[-1]),
        )
        return cls(need=need, bars=bars, index=index)


@dataclass(frozen=True)
class _CatalogArrays:
    catalog: Catalog
    providers: CustomDataProviderMap
    registry: CustomDataRegistry | None


class SleeveArrays:
    """Ensure and project every array declared by a Sleeve DataContract."""

    def __init__(
        self,
        *,
        catalog: _CatalogArrays | None,
    ) -> None:
        self._catalog = catalog

    @classmethod
    def bar_only(cls) -> SleeveArrays:
        """Build an assembler for contracts containing only bar-derived arrays."""
        return cls(catalog=None)

    @classmethod
    def prepared(
        cls,
        *,
        catalog: Catalog,
        registry: CustomDataRegistry | None = None,
    ) -> SleeveArrays:
        """Build an assembler which accepts only already-covered catalog data."""
        return cls(catalog=_CatalogArrays(catalog, {}, registry))

    @classmethod
    def live(
        cls,
        *,
        catalog: Catalog,
        providers: CustomDataProviderMap,
        registry: CustomDataRegistry | None = None,
    ) -> SleeveArrays:
        """Build an assembler which heals catalog gaps through live providers."""
        return cls(catalog=_CatalogArrays(catalog, dict(providers), registry))

    def ensure(self, need: ArrayNeed) -> None:
        """Warm missing Catalog intervals for every non-Bar array kind."""
        custom_names = _custom_names(need.names)
        if not custom_names:
            return
        catalog = self._require_catalog()
        ensure_arrays(
            dict.fromkeys(need.instrument_ids, custom_names),
            start=need.start,
            end=need.end,
            providers=catalog.providers,
            catalog=catalog.catalog,
            registry=catalog.registry,
        )

    def project(self, grid: SleeveArrayGrid) -> dict[str, pd.DataFrame]:
        """Read every required panel on the grid without writes or provider calls."""
        panels = {
            name: _bar_panel(grid, name)
            for name in grid.need.names
            if is_bar_derived_array(name)
        }
        custom_names = _custom_names(grid.need.names)
        if custom_names:
            catalog = self._require_catalog()
            panels.update(
                project_custom_arrays(
                    custom_names,
                    grid.need.instrument_ids,
                    index=grid.index,
                    catalog=catalog.catalog,
                    registry=catalog.registry,
                )
            )
        ordered = {name: panels[name] for name in grid.need.names}
        _validate_panels(ordered, grid)
        return ordered

    def _require_catalog(self) -> _CatalogArrays:
        if self._catalog is None:
            raise CustomArrayCatalogNotConfiguredError(
                "catalog-backed arrays require a configured catalog path"
            )
        return self._catalog


_BAR_ARRAY_ACCESSORS: dict[str, Callable[[MarketBar], float]] = {
    "Open": lambda bar: bar.open,
    "High": lambda bar: bar.high,
    "Low": lambda bar: bar.low,
    "Close": lambda bar: bar.close,
    "Volume": lambda bar: bar.volume,
}


def _custom_names(names: Sequence[str]) -> tuple[str, ...]:
    return tuple(name for name in names if not is_bar_derived_array(name))


def _bar_panel(grid: SleeveArrayGrid, name: str) -> pd.DataFrame:
    accessor = _BAR_ARRAY_ACCESSORS[name]
    series = {
        instrument_id: pd.Series(
            [accessor(bar) for bar in grid.bars[instrument_id]],
            index=pd.DatetimeIndex([bar.ts_event for bar in grid.bars[instrument_id]]),
            dtype=float,
        )
        for instrument_id in grid.need.instrument_ids
    }
    return pd.DataFrame(series, index=grid.index).reindex(
        columns=grid.need.instrument_ids
    )


def _validate_panels(
    panels: Mapping[str, pd.DataFrame],
    grid: SleeveArrayGrid,
) -> None:
    if tuple(panels) != grid.need.names:
        raise SleeveArrayShapeError("projected array names do not match the contract")
    for name, panel in panels.items():
        if not panel.index.equals(grid.index):
            raise SleeveArrayShapeError(f"{name} does not use the Sleeve union index")
        if tuple(panel.columns) != grid.need.instrument_ids:
            raise SleeveArrayShapeError(f"{name} does not use the declared instruments")


__all__ = [
    "ArrayNeed",
    "CustomArrayCatalogNotConfiguredError",
    "EmptySleeveArrayGridError",
    "InvalidArrayIntervalError",
    "SleeveArrayGrid",
    "SleeveArrayShapeError",
    "SleeveArrays",
]
