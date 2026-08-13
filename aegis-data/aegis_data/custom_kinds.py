from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nautilus_trader.core.data import Data


@dataclass(frozen=True)
class ArrayProjection:
    value_array: str
    availability_array: str
    age_array: str
    value_attribute: str

    @property
    def array_names(self) -> tuple[str, ...]:
        return (self.value_array, self.availability_array, self.age_array)


@dataclass(frozen=True)
class HistoricalDataCapability:
    """Static declaration that a configured historical adapter may exist."""


@dataclass(frozen=True)
class LiveDataCapability:
    """Static declaration that a configured live adapter may exist."""


@dataclass(frozen=True)
class CustomDataKind:
    """One complete static Custom Data declaration."""

    record_type: type[Data]
    projection: ArrayProjection
    historical: HistoricalDataCapability | None
    live: LiveDataCapability | None = None

    @property
    def array_names(self) -> tuple[str, ...]:
        return self.projection.array_names

    @property
    def provisioned(self) -> bool:
        return self.historical is not None


class InvalidCustomDataRegistryError(ValueError):
    """Kind declarations collide on a record type or array name."""


@dataclass(frozen=True)
class CustomDataRegistry:
    kinds: tuple[CustomDataKind, ...] = ()

    def __post_init__(self) -> None:
        record_types = [kind.record_type for kind in self.kinds]
        array_names = [name for kind in self.kinds for name in kind.array_names]
        if len(record_types) != len(set(record_types)):
            raise InvalidCustomDataRegistryError("duplicate Custom Data record type")
        if len(array_names) != len(set(array_names)):
            raise InvalidCustomDataRegistryError("duplicate Custom Data array name")

    @property
    def known_array_names(self) -> frozenset[str]:
        return frozenset(name for kind in self.kinds for name in kind.array_names)

    @property
    def vocabulary(self) -> frozenset[str]:
        return frozenset(
            name
            for kind in self.kinds
            if kind.provisioned
            for name in kind.array_names
        )

    @property
    def availability_by_value(self) -> dict[str, str]:
        return {
            kind.projection.value_array: kind.projection.availability_array
            for kind in self.kinds
        }

    def kind_for(self, record_type: type[Data]) -> CustomDataKind:
        for kind in self.kinds:
            if kind.record_type is record_type:
                return kind
        raise KeyError(record_type)

    def kinds_for_arrays(self, array_names: Sequence[str]) -> tuple[CustomDataKind, ...]:
        requested = set(array_names)
        kinds = tuple(
            kind for kind in self.kinds if requested.intersection(kind.array_names)
        )
        resolved = {name for kind in kinds for name in kind.array_names}
        unknown = sorted(requested - resolved)
        if unknown:
            raise KeyError(tuple(unknown))
        return kinds


DECLARED_CUSTOM_DATA_KINDS = CustomDataRegistry()


def declared_custom_data_kinds() -> CustomDataRegistry:
    """Return the process's immutable import-time kind declaration set."""
    return DECLARED_CUSTOM_DATA_KINDS


__all__ = [
    "ArrayProjection",
    "CustomDataKind",
    "CustomDataRegistry",
    "HistoricalDataCapability",
    "InvalidCustomDataRegistryError",
    "LiveDataCapability",
    "declared_custom_data_kinds",
]
