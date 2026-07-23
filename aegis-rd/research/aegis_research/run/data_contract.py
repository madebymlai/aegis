"""Run data contract.

Owns the pre-load Array contract and the pure projections from the one loaded
``RunData`` value into Candidate identity and store artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    ConfigValidationError,
    ConfigValidationIssue,
    merge_data_arrays,
)
from research.aegis_research.run.data import RunData


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


def candidate_data_identity(
    run_data: RunData,
    array_contract: DataArrayContract,
) -> dict[str, Any]:
    """Project the structural data identity hashed into every Candidate key."""
    identity = run_data.identity
    return to_builtin(
        {
            "schema_version": "candidate_data_identity.v4",
            "requested_instrument_ids": identity.requested_instrument_ids,
            "tradeables": [
                {
                    "instrument_id": tradeable.instrument_id,
                    **(
                        {"continuous_root": tradeable.continuous_root}
                        if tradeable.continuous_root is not None
                        else {}
                    ),
                }
                for tradeable in identity.tradeables
            ],
            "loaded_arrays": identity.loaded_arrays,
            "timeframe": identity.timeframe,
            "start": identity.start,
            "end": identity.end,
            "missing_index": identity.missing_index,
            "rows": identity.rows,
            "index_start": identity.index_start,
            "index_end": identity.index_end,
            "source": identity.source,
            "catalog_path": identity.catalog_path,
            "currency_by_instrument_id": identity.currency_by_instrument_id,
            "size_increment_by_instrument": identity.size_increment_by_instrument,
            "distribution_coverage": identity.distribution_coverage,
            "adjustment_mode": identity.adjustment_mode,
            "array_contract": array_contract.metadata(),
        }
    )


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
