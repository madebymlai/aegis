from __future__ import annotations

from research.aegis_research.candidates.identity import (
    build_candidate_store_provenance,
    candidate_store_namespace,
)
from research.aegis_research.candidates.models import CandidateSet
from research.aegis_research.candidates.records import candidate_rows_from_result
from research.aegis_research.configuration import RunConfig, to_builtin
from research.aegis_research.run._stages.execution import ExecutionResult
from research.aegis_research.run._stages.setup import SetupResult
from research.aegis_research.run.data_contract import DataArrayContract, candidate_data_identity
from research.aegis_research.run.identity import RunId


def derive_candidate_set(
    *,
    run_id: RunId,
    config: RunConfig,
    setup: SetupResult,
    execution: ExecutionResult,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
) -> CandidateSet:
    candidates = candidate_rows_from_result(
        execution.optimization_result,
        source_identity=setup.optimization_source.identity,
        data_identity=candidate_data_identity(setup.run_data, array_contract),
        selection_identity=execution.selection_identity,
        book_settings=to_builtin(config.portfolio),
        store_namespace=candidate_store_namespace(),
    )
    provenance = build_candidate_store_provenance(
        run_id,
        optimization_source=setup.optimization_source.identity,
        run_data=setup.run_data,
        array_contract=array_contract,
        config=config,
        metric_registry_fingerprint=metric_registry_fingerprint,
        selection_identity=execution.selection_identity,
    )
    return CandidateSet.create(
        run_id=run_id,
        candidates=candidates,
        provenance=provenance,
    )


__all__ = ["derive_candidate_set"]
