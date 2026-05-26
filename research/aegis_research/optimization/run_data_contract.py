"""Run data contract.

Builds the data array contract, data evidence payload, and candidate
data identity for orchestrated optimization runs.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
    build_data_array_contract,
    data_array_evidence_payload,
    merge_data_arrays,
)


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
