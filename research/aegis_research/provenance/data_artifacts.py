"""Data-stage artifact writer.

Writes the data metadata artifact captured during the data loading stage
of a strategy Run.
"""

from __future__ import annotations

from pathlib import Path

from research.aegis_research.atomic_write import write_json
from research.aegis_research.market_data.contracts import MarketDataResult
from research.aegis_research.provenance.recorder import RunRecorder


def write_data_metadata_artifact(recorder: RunRecorder, data_result: MarketDataResult) -> None:
    artifact_id = "data.metadata"
    role = "data_metadata"
    producer_stage = "data"
    path = "data_metadata.json"
    schema_version = "data_metadata.v2"

    recorder.artifacts.plan_artifact(
        artifact_id=artifact_id,
        role=role,
        artifact_type="json",
        producer_stage=producer_stage,
        path=path,
        schema_version=schema_version,
    )
    target = recorder.run_dir / path
    recorder.artifacts.begin_artifact_write(artifact_id)
    try:
        write_json(target, data_result.metadata)
        recorder.artifacts.complete_existing_file(artifact_id)
    except Exception as error:
        try:
            _fail_artifact_write(recorder, artifact_id=artifact_id, target=target, error=error)
        except Exception as failure_error:
            error.add_note(f"failed to mark artifact {artifact_id!r} as failed: {failure_error}")
        raise


def _fail_artifact_write(
    recorder: RunRecorder,
    *,
    artifact_id: str,
    target: Path,
    error: Exception,
) -> None:
    if target.exists():
        target.unlink()
    recorder.artifacts.fail_artifact(
        artifact_id,
        {"error_type": type(error).__name__, "message": str(error)[:1000]},
    )
