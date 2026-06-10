from __future__ import annotations

from pathlib import Path

from research.aegis_research.data import close_from_ohlcv, load_market_data_result
from research.aegis_research.provenance.manifest import RunStatus
from research.aegis_research.provenance.recorder import RunRecorder
from tests.support.research.aegis_research.factories import make_data_config


def test_recorder_run_refs_returns_six_field_snapshot(tmp_path: Path) -> None:
    """RunRecorder.run_refs() returns a six-field snapshot of current Manifest state.

    Fields: run_id, run_dir, manifest_path, status, started_at, finished_at.
    The snapshot tracks state changes through mark methods — status and
    finished_at reflect the terminal mark-methods.
    """
    recorder = RunRecorder.start(
        run_dir=tmp_path / "run-refs",
        run_id="run-refs",
        run_label="baseline",
        mode="new",
        config={"schema_version": 1},
    )

    # Running state — finished_at is absent.
    refs = recorder.run_refs()
    assert refs["run_id"] == "run-refs"
    assert refs["run_dir"] == str(tmp_path / "run-refs")
    assert refs["manifest_path"] == str(tmp_path / "run-refs" / "manifest.json")
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
        run_dir=tmp_path / "run-failed",
        run_id="run-failed",
        run_label="baseline",
        mode="new",
        config={"schema_version": 1},
    )
    failed.mark_run_failed(diagnostic={"error": "boom"})
    refs = failed.run_refs()
    assert refs["status"] == RunStatus.FAILED
    assert refs["finished_at"] is not None

    # Interrupted
    interrupted = RunRecorder.start(
        run_dir=tmp_path / "run-int",
        run_id="run-int",
        run_label="baseline",
        mode="new",
        config={"schema_version": 1},
    )
    interrupted.mark_run_interrupted(diagnostic={"signal": "SIGINT"})
    refs = interrupted.run_refs()
    assert refs["status"] == RunStatus.INTERRUPTED
    assert refs["finished_at"] is not None


def test_data_stage_result_exposes_metadata_without_recorder_ids() -> None:
    result = load_market_data_result(make_data_config(rows=10, symbols=["SYN"]))

    assert result.native_data.feature_oriented
    assert close_from_ohlcv(result.native_data).shape == (10, 1)
    assert result.metadata["source"] == "synthetic"
    assert result.metadata["shape"]["rows"] == 10
    assert "artifact_id" not in result.metadata
