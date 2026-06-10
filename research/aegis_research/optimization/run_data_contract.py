"""Run data contract.

Owns the data array contract — which arrays a Run requires versus what its
config declares — and builds the data evidence payload and candidate data
identity for orchestrated optimization runs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    ConfigValidationError,
    ConfigValidationIssue,
    merge_data_arrays,
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


def build_run_data_array_contract(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> DataArrayContract:
    return build_data_array_contract(
        configured_arrays=config.data.effective_arrays,
        component_required_arrays=build_run_required_arrays(config, component_registry),
        pipeline_required_arrays=("Close", "Open"),
    )


def build_run_required_arrays(
    config: Any,
    component_registry: FrozenComponentRegistry,
) -> tuple[str, ...]:
    required = [
        component_registry.get(ComponentSelection("strategies", config.strategy.id)).input_names
    ]
    for ref in config.indicators:
        required.append(
            component_registry.get(ComponentSelection("indicators", ref.id)).input_names
        )
    return merge_data_arrays(*required)


def build_run_data_evidence_payload(
    data_result: Any,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    return data_array_evidence_payload(data_result, array_contract) | {
        "strategy_consumed_runner_data": True,
        "strategy_data_binding": "runner_data_bundle",
    }


def build_candidate_data_identity(
    data_result: Any,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    metadata = data_result.metadata
    return {
        "schema_version": "candidate_data_identity.v1",
        "source": metadata.get("source"),
        "requested_symbols": metadata.get("requested_symbols"),
        "symbols": metadata.get("symbols"),
        "timeframe": metadata.get("timeframe"),
        "effective_arrays": metadata.get("effective_arrays"),
        "loaded_arrays": metadata.get("loaded_arrays"),
        "shape": metadata.get("shape"),
        "index_start": metadata.get("index_start"),
        "index_end": metadata.get("index_end"),
        "index_evidence": metadata.get("index_evidence"),
        "source_metadata": metadata.get("source_metadata"),
        "array_contract": array_contract.metadata(),
    }
