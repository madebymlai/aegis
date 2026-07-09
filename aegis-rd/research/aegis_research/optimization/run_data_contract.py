"""Run data contract.

Owns the data array contract — which arrays a Run requires versus what its
config declares — and builds the data evidence payload and candidate data
identity for orchestrated optimization runs.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def data_array_evidence_payload(
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    metadata = data_result.metadata
    loaded_arrays = [d.name for d in metadata.arrays if d.loaded]
    unavailable_arrays = [d.name for d in metadata.arrays if d.required and not d.loaded]
    return {
        **array_contract.metadata(),
        "authored_arrays": metadata.request.authored_arrays,
        "effective_arrays": metadata.request.effective_arrays,
        "loaded_arrays": loaded_arrays,
        "unavailable_arrays": unavailable_arrays,
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
    return (
        data_array_evidence_payload(data_result, array_contract)
        | {
            "strategy_consumed_runner_data": True,
            "strategy_data_binding": "runner_data_bundle",
        }
        | _adjustment_mode_fact(data_result)
    )


def build_candidate_data_identity(
    data_result: Any,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    metadata = data_result.metadata
    loaded_arrays = [d.name for d in metadata.arrays if d.loaded]
    return {
        "schema_version": "candidate_data_identity.v3",
        "requested_instrument_ids": metadata.request.requested_instrument_ids,
        "instrument_ids": metadata.coverage.instrument_ids,
        "timeframe": metadata.request.timeframe,
        "effective_arrays": metadata.request.effective_arrays,
        "loaded_arrays": loaded_arrays,
        "rows": metadata.coverage.rows,
        "index_start": metadata.coverage.start,
        "index_end": metadata.coverage.end,
        "index_evidence": metadata.provenance.index_evidence,
        "source_metadata": metadata.provenance.source_metadata,
        "array_contract": array_contract.metadata(),
        # Present iff futures were materialised: otherwise-identical ratio and
        # spread Runs must produce different Candidate keys.
        **_adjustment_mode_fact(data_result),
    }


def _adjustment_mode_fact(data_result: Any) -> dict[str, str]:
    mode = data_result.adjustment_mode
    if mode is None:
        return {}
    return {"adjustment_mode": mode.value}
