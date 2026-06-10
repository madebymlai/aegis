"""Pipeline publishing stage.

Turns the three representative candidates into role-tagged candidate rows
and publishes them to the candidate store.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.aegis_research.configuration import (
    RunConfig,
    to_builtin,
)
from research.aegis_research.data import (
    MarketDataResult,
)
from research.aegis_research.data_arrays import (
    DataArrayContract,
)
from research.aegis_research.optimization.candidate_publishing import (
    build_candidate_store_provenance,
    candidate_store_namespace,
    publish_candidates,
)
from research.aegis_research.optimization.evidence import candidate_rows_from_result
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    EvidenceSection,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.execution import ExecutionResult
from research.aegis_research.optimization.run_data_contract import (
    build_candidate_data_identity,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.provenance.recorder import RunRecorder


@dataclass(frozen=True)
class PublishingResult:
    """Typed hand-off from the pipeline publishing stage."""

    candidate_rows: tuple[dict[str, Any], ...]
    candidate_store_provenance: Mapping[str, Any]


def run_pipeline_publishing(
    *,
    config: RunConfig,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    array_contract: DataArrayContract,
    optimization_source: OptimizationSource,
    execution: ExecutionResult,
    run_evidence: RunEvidence,
    store_path: Path,
    metric_registry_fingerprint: str | None,
) -> PublishingResult:
    """Build the three candidate rows and publish them to the candidate store."""
    try:
        store_namespace = candidate_store_namespace()
        candidate_rows = candidate_rows_from_result(
            execution.optimization_result,
            source_identity=optimization_source.evidence,
            data_identity=build_candidate_data_identity(data_result, array_contract),
            portfolio_policy=to_builtin(config.portfolio),
            store_namespace=store_namespace,
        )
        run_evidence.record(EvidenceSection.CANDIDATES, candidate_rows)
        candidate_store_provenance = build_candidate_store_provenance(
            recorder,
            optimization_source=optimization_source.evidence,
            data_result=data_result,
            array_contract=array_contract,
            config=config,
            metric_registry_fingerprint=metric_registry_fingerprint,
        )
        publish_candidates(
            store_path,
            run_id=recorder.manifest.run_id,
            candidate_rows=candidate_rows,
            ranking_metric=config.ranking.metric,
            provenance=candidate_store_provenance,
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.PUBLISHING, error)
        raise

    return PublishingResult(
        candidate_rows=tuple(candidate_rows),
        candidate_store_provenance=candidate_store_provenance,
    )
