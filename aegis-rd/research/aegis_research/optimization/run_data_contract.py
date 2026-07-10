"""Run data contract.

Owns the facts about what data a Run ran on: the data array contract —
which arrays a Run requires versus what its config declares — and, once
market data is loaded, the ``RunDataFacts`` value whose projections build
the data evidence payload, the candidate data identity, and the data
metadata artifact payload for orchestrated optimization runs (ADR-0025).
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


@dataclass(frozen=True)
class RunDataFacts:
    """The facts about what data this Run ran on (ADR-0025).

    Born by composition in the orchestrator immediately after market data
    loads; the contract keeps its separate pre-load life. Every pure
    projection of these facts lives here — consumers take the value whole
    and call a projection instead of assembling payloads from the parts.
    """

    data_result: MarketDataResult
    array_contract: DataArrayContract
    metric_registry_fingerprint: str | None

    def evidence_payload(self) -> dict[str, Any]:
        """The Run data evidence payload for the Evidence baseline and artifact."""
        return (
            self._array_evidence_payload()
            | {
                "strategy_consumed_runner_data": True,
                "strategy_data_binding": "runner_data_bundle",
            }
            | self._adjustment_mode_fact()
        )

    def candidate_data_identity(self) -> dict[str, Any]:
        """The data identity hashed into every Candidate key."""
        metadata = self.data_result.metadata
        return {
            "schema_version": "candidate_data_identity.v3",
            "requested_instrument_ids": metadata.request.requested_instrument_ids,
            "instrument_ids": metadata.coverage.instrument_ids,
            "timeframe": metadata.request.timeframe,
            "effective_arrays": metadata.request.effective_arrays,
            "loaded_arrays": self._loaded_arrays(),
            "rows": metadata.coverage.rows,
            "index_start": metadata.coverage.start,
            "index_end": metadata.coverage.end,
            "index_evidence": metadata.provenance.index_evidence,
            "source_metadata": metadata.provenance.source_metadata,
            "array_contract": self.array_contract.metadata(),
            # Present iff futures were materialised: otherwise-identical ratio and
            # spread Runs must produce different Candidate keys.
            **self._adjustment_mode_fact(),
        }

    def metadata_artifact_payload(self) -> dict[str, Any]:
        """The data metadata artifact payload: serialised metadata plus contract facts."""
        return to_builtin(self.data_result.metadata) | self.array_contract.metadata()

    def _array_evidence_payload(self) -> dict[str, Any]:
        metadata = self.data_result.metadata
        unavailable_arrays = [d.name for d in metadata.arrays if d.required and not d.loaded]
        return {
            **self.array_contract.metadata(),
            "authored_arrays": metadata.request.authored_arrays,
            "effective_arrays": metadata.request.effective_arrays,
            "loaded_arrays": self._loaded_arrays(),
            "unavailable_arrays": unavailable_arrays,
            "quality_state": self.data_result.quality.state,
        }

    def _loaded_arrays(self) -> list[str]:
        return [d.name for d in self.data_result.metadata.arrays if d.loaded]

    def _adjustment_mode_fact(self) -> dict[str, str]:
        mode = self.data_result.adjustment_mode
        if mode is None:
            return {}
        return {"adjustment_mode": mode.value}


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
