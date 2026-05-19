from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from research.aegis_research.configuration.schema import (
    ConfigValidationError,
    ConfigValidationIssue,
)
from research.aegis_research.market_data.contracts import MarketDataResult


@dataclass(frozen=True)
class DataArrayContract:
    configured_arrays: tuple[str, ...]
    component_required_arrays: tuple[str, ...] = ()
    pipeline_required_arrays: tuple[str, ...] = ()

    @property
    def required_arrays(self) -> tuple[str, ...]:
        return merge_data_arrays(self.component_required_arrays, self.pipeline_required_arrays)

    @property
    def missing_arrays(self) -> tuple[str, ...]:
        configured = set(self.configured_arrays)
        return tuple(feature for feature in self.required_arrays if feature not in configured)

    def assert_configured(self) -> None:
        if not self.missing_arrays:
            return
        raise ConfigValidationError(
            [
                ConfigValidationIssue(
                    "data.arrays",
                    f"missing required data arrays: {list(self.missing_arrays)}",
                )
            ]
        )

    def metadata(self) -> dict[str, list[str]]:
        return {
            "configured_arrays": list(self.configured_arrays),
            "component_required_arrays": list(self.component_required_arrays),
            "pipeline_required_arrays": list(self.pipeline_required_arrays),
            "contract_required_arrays": list(self.required_arrays),
            "missing_required_arrays": list(self.missing_arrays),
        }


def build_data_array_contract(
    *,
    configured_arrays: tuple[str, ...],
    component_required_arrays: tuple[str, ...] = (),
    pipeline_required_arrays: tuple[str, ...] = (),
) -> DataArrayContract:
    return DataArrayContract(
        configured_arrays=configured_arrays,
        component_required_arrays=merge_data_arrays(component_required_arrays),
        pipeline_required_arrays=merge_data_arrays(pipeline_required_arrays),
    )


def merge_data_arrays(*array_groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in array_groups:
        for feature in group:
            if feature in seen:
                continue
            merged.append(feature)
            seen.add(feature)
    return tuple(merged)


def with_data_array_contract_metadata(
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
) -> MarketDataResult:
    metadata = dict(data_result.metadata)
    metadata.update(array_contract.metadata())
    return replace(data_result, metadata=metadata)


def data_array_evidence_payload(
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    metadata = data_result.metadata
    return {
        **array_contract.metadata(),
        "authored_arrays": metadata.get("authored_arrays"),
        "effective_arrays": metadata.get("effective_arrays"),
        "loaded_arrays": metadata.get("loaded_arrays"),
        "unavailable_arrays": metadata.get("unavailable_arrays"),
        "quality_state": data_result.quality.state,
    }
