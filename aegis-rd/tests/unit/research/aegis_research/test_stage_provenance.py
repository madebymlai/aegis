from __future__ import annotations

from pathlib import Path

from research.aegis_research.provenance.manifest import RunFailure, RunStage, RunStatus
from research.aegis_research.provenance.recorder import RunRecorder
from tests.support.research.aegis_research.factories import make_run_data


def test_recorder_run_refs_returns_five_field_snapshot(tmp_path: Path) -> None:
    """run_refs() returns run_id, manifest_path, status, started_at, and finished_at.

    The snapshot tracks Manifest state changes through mark methods — status
    and finished_at reflect the terminal mark-methods.
    """
    recorder = RunRecorder.start(
        manifest_path=tmp_path / "run-refs.json",
        run_id="run-refs",
        config={"schema_version": 1},
    )

    # Running state — finished_at is absent.
    refs = recorder.run_refs()
    assert refs["run_id"] == "run-refs"
    assert "run_dir" not in refs
    assert refs["manifest_path"] == str(tmp_path / "run-refs.json")
    assert refs["status"] == RunStatus.RUNNING
    assert refs["started_at"] is not None
    assert refs["finished_at"] is None

    # Completed state — status and finished_at updated.
    recorder.mark_run_completed()
    refs = recorder.run_refs()
    assert refs["status"] == RunStatus.COMPLETED
    assert refs["finished_at"] is not None


def test_recorder_run_refs_reflects_failed_and_interrupted_terminal_states(
    tmp_path: Path,
) -> None:
    """run_refs() reflects the terminal status and finished_at for failed and interrupted runs."""
    # Failed
    failed = RunRecorder.start(
        manifest_path=tmp_path / "run-failed.json",
        run_id="run-failed",
        config={"schema_version": 1},
    )
    failed.mark_run_failed(stage=RunStage.RUN, error=RuntimeError("boom"))
    refs = failed.run_refs()
    assert refs["status"] == RunStatus.FAILED
    assert refs["finished_at"] is not None
    assert isinstance(failed.manifest.failure, RunFailure)

    # Interrupted
    interrupted = RunRecorder.start(
        manifest_path=tmp_path / "run-int.json",
        run_id="run-int",
        config={"schema_version": 1},
    )
    interrupted.mark_run_interrupted(stage=RunStage.RUN, error=KeyboardInterrupt())
    refs = interrupted.run_refs()
    assert refs["status"] == RunStatus.INTERRUPTED
    assert refs["finished_at"] is not None


def test_run_data_exposes_evidence_without_recorder_ids() -> None:
    result = make_run_data()

    assert result.bundle.array("Close").shape == (2, 1)
    assert result.evidence.rows == 2
