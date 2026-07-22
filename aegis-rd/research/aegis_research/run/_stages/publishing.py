"""Pipeline publishing stage.

Turns the three representative candidates into role-tagged candidate rows
and publishes them to the candidate store.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.aegis_research.candidates.evidence import candidate_rows_from_result
from research.aegis_research.candidates.identity import (
    build_candidate_store_provenance,
    candidate_store_namespace,
)
from research.aegis_research.candidates.store import (
    PUBLICATION_PENDING,
    CandidateStore,
)
from research.aegis_research.configuration import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.run._stages.execution import ExecutionResult
from research.aegis_research.run.data import RunData
from research.aegis_research.run.data_contract import (
    DataArrayContract,
    candidate_data_identity,
)
from research.aegis_research.run.evidence import (
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.run.record.manifest import RunStage
from research.aegis_research.run.record.recorder import RunRecorder


@dataclass(frozen=True)
class PublishingResult:
    """Typed hand-off from the pipeline publishing stage."""

    candidate_rows: tuple[dict[str, Any], ...]
    candidate_store_provenance: Mapping[str, Any]


def run_pipeline_publishing(
    *,
    config: RunConfig,
    recorder: RunRecorder,
    run_data: RunData,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    optimization_source: OptimizationSource,
    execution: ExecutionResult,
    run_evidence: RunEvidence,
    store_path: Path,
) -> PublishingResult:
    """Build the three candidate rows and publish them to the candidate store."""
    run_evidence.enter_stage(RunStage.PUBLISHING)
    try:
        store_namespace = candidate_store_namespace()
        candidate_rows = candidate_rows_from_result(
            execution.optimization_result,
            source_identity=optimization_source.evidence,
            data_identity=candidate_data_identity(run_data, array_contract),
            selection_identity=execution.selection_identity,
            book_settings=to_builtin(config.portfolio),
            store_namespace=store_namespace,
        )
        run_evidence.record(EvidenceSection.CANDIDATES, candidate_rows)
        candidate_store_provenance = build_candidate_store_provenance(
            recorder,
            optimization_source=optimization_source.evidence,
            run_data=run_data,
            array_contract=array_contract,
            config=config,
            metric_registry_fingerprint=metric_registry_fingerprint,
            selection_identity=dict(execution.selection_identity),
        )
        with CandidateStore(store_path) as candidate_store:
            candidate_store.insert_completed_run(
                run_id=recorder.manifest.run_id,
                candidate_rows=candidate_rows,
                provenance=candidate_store_provenance,
                publication_state=PUBLICATION_PENDING,
            )
    except Exception:
        run_evidence.persist_partial()
        raise

    return PublishingResult(
        candidate_rows=tuple(candidate_rows),
        candidate_store_provenance=candidate_store_provenance,
    )
