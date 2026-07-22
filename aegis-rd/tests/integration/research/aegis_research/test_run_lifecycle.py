from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from research.aegis_research.run.data import (
    RunDataFailureEvidence,
    RunDataUnavailable,
)
from research.aegis_research.run.pipeline import run_strategy_sweep
from research.aegis_research.run.record.manifest import RunStatus
from research.aegis_research.run.record.recorder import RunRecorder
from research.aegis_research.run.record.run_store import RunCollisionError, RunStore
from tests.support.research.aegis_research.factories import make_run_data
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config


def test_run_recorder_starts_and_completes_manifest(tmp_path: Path) -> None:
    recorder = RunRecorder.start(
        manifest_path=tmp_path / "run-1.json",
        run_id="run-1",
        config={"schema_version": 1},
    )

    assert recorder.manifest_path.exists()
    running_manifest = json.loads(recorder.manifest_path.read_text())
    assert running_manifest["run"]["status"] == RunStatus.RUNNING

    recorder.mark_run_completed()

    completed_manifest = json.loads(recorder.manifest_path.read_text())
    assert completed_manifest["run"]["status"] == RunStatus.COMPLETED
    assert completed_manifest["run"]["finished_at"]
    assert "failure" not in completed_manifest["run"]


def test_run_store_rejects_existing_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start_run(
        config={"schema_version": 1},
        run_id="fixed-run",
    )
    assert (tmp_path / "fixed-run.json").is_file()
    assert not (tmp_path / "fixed-run").exists()

    with pytest.raises(RunCollisionError):
        store.start_run(
            config={"schema_version": 1},
            run_id="fixed-run",
        )


def test_run_store_claims_duplicate_run_id_atomically(tmp_path: Path) -> None:
    contenders = 16
    barrier = Barrier(contenders)

    def start_run() -> RunRecorder | BaseException:
        barrier.wait()
        try:
            return RunStore(tmp_path).start_run(
                config={"schema_version": 1},
                run_id="contended-run",
            )
        except BaseException as error:
            return error

    with ThreadPoolExecutor(max_workers=contenders) as executor:
        results = list(executor.map(lambda _index: start_run(), range(contenders)))

    assert sum(isinstance(result, RunRecorder) for result in results) == 1
    assert sum(isinstance(result, RunCollisionError) for result in results) == contenders - 1
    assert json.loads((tmp_path / "contended-run.json").read_text())["run"]["id"] == (
        "contended-run"
    )


def test_run_store_does_not_misreport_invalid_root_as_run_collision(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.write_text("not a directory")

    with pytest.raises(FileExistsError) as exc_info:
        RunStore(root).start_run(config={"schema_version": 1}, run_id="run-1")

    assert type(exc_info.value) is FileExistsError


@pytest.mark.parametrize("run_id", ["../escape", "/tmp/escape", "nested/escape", "bad id"])
def test_run_store_rejects_unsafe_run_ids(tmp_path: Path, run_id: str) -> None:
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match="run_id"):
        store.start_run(
            config={"schema_version": 1},
            run_id=run_id,
        )

    assert not any(tmp_path.iterdir())


def test_run_store_rejects_relative_symlinked_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside-runs"
    outside.mkdir()
    (tmp_path / "runs").symlink_to(outside, target_is_directory=True)
    store = RunStore("runs")

    with pytest.raises(ValueError, match="symlinked"):
        store.start_run(
            config={"schema_version": 1},
            run_id="escape-run",
        )

    assert not (outside / "escape-run.json").exists()


def test_strategy_run_initializes_manifest_before_data_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def fail_after_manifest(_config, **_kwargs):
        manifest_path = tmp_path / "runs" / "fixed-run.json"
        assert manifest_path.exists()
        raise RuntimeError("data stage failed")

    monkeypatch.setattr("research.aegis_research.run.pipeline.load_run_data", fail_after_manifest)

    with pytest.raises(RuntimeError, match="data stage failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="fixed-run",
        )

    manifest = json.loads((tmp_path / "runs" / "fixed-run.json").read_text())
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["failure"] == {
        "stage": "data",
        "error_type": "RuntimeError",
        "message": "data stage failed",
    }
    assert "stages" not in manifest


def test_environmental_data_evidence_is_persisted_before_terminal_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)
    failure = RunDataFailureEvidence(
        schema_version="run_data_failure.v1",
        requested_instrument_ids=(),
        requested_arrays=("Close",),
        continuous_roots=("ES",),
        timeframe="1D",
        start="2024-01-01",
        end="2024-01-03",
        catalog_path="/catalog",
        error_type="CatalogCoverageGapError",
        message="catalog gap",
        source="nautilus_catalog",
    )
    original_mark_failed = RunRecorder.mark_run_failed

    def fail_environmentally(_config, **_kwargs):
        raise RunDataUnavailable(failure)

    def assert_evidence_precedes_terminal(self, *, stage, error):
        assert self.manifest.evidence["data"] == {
            "schema_version": "run_data_failure.v1",
            "requested_instrument_ids": [],
            "requested_arrays": ["Close"],
            "continuous_roots": ["ES"],
            "timeframe": "1D",
            "start": "2024-01-01",
            "end": "2024-01-03",
            "catalog_path": "/catalog",
            "error_type": "CatalogCoverageGapError",
            "message": "catalog gap",
            "source": "nautilus_catalog",
        }
        original_mark_failed(self, stage=stage, error=error)

    monkeypatch.setattr(
        "research.aegis_research.run.pipeline.load_run_data",
        fail_environmentally,
    )
    monkeypatch.setattr(RunRecorder, "mark_run_failed", assert_evidence_precedes_terminal)

    with pytest.raises(RunDataUnavailable, match="catalog gap"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="environmental-failure",
        )


def test_strategy_run_marks_failed_when_on_run_refs_callback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def fail_callback(_refs):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="callback-failed-run",
            on_run_refs=fail_callback,
        )

    manifest = json.loads((tmp_path / "runs" / "callback-failed-run.json").read_text())
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["failure"] == {
        "stage": "run",
        "error_type": "RuntimeError",
        "message": "callback failed",
    }


def test_strategy_run_records_interruption_at_active_optimization_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    resolved = build_resolved_run_config(tmp_path)

    def interrupt_setup(**_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "research.aegis_research.run.pipeline.run_pipeline_setup",
        interrupt_setup,
    )
    monkeypatch.setattr(
        "research.aegis_research.run.pipeline.load_run_data",
        lambda *_args, **_kwargs: make_run_data(),
    )

    with pytest.raises(KeyboardInterrupt):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="setup-interrupted-run",
        )

    manifest = json.loads((tmp_path / "runs" / "setup-interrupted-run.json").read_text())
    assert manifest["run"]["failure"]["stage"] == "setup"


def test_failed_run_diagnostic_is_length_clipped_not_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REMOTE_TOKEN", "super-secret-token")
    resolved = build_resolved_run_config(
        tmp_path,
        data={
            "start": "2020-01-01",
            "end": "2021-01-01",
            "timeframe": "1D",
        },
    )

    long_message = "provider returned super-secret-token " + "x" * 2000

    def fail_with_secret(_config, **_kwargs):
        raise RuntimeError(long_message)

    monkeypatch.setattr("research.aegis_research.run.pipeline.load_run_data", fail_with_secret)

    with pytest.raises(RuntimeError, match="provider returned"):
        run_strategy_sweep(
            resolved,
            component_registry=resolved.component_registry,
            run_id="secret-failed-run",
        )

    manifest = json.loads((tmp_path / "runs" / "secret-failed-run.json").read_text())
    diagnostic = manifest["run"]["failure"]
    assert diagnostic["stage"] == "data"
    assert diagnostic["message"] == long_message[:1000]
    assert "<redacted>" not in diagnostic["message"]
    assert diagnostic["message"].startswith("provider returned super-secret-token")
