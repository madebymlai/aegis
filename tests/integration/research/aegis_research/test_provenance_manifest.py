from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research.aegis_research.provenance.artifacts import ArtifactRegistry
from research.aegis_research.provenance.evidence import (
    capture_environment_evidence,
    capture_git_evidence,
    capture_run_start_evidence,
)
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ArtifactVisibility,
    ManifestValidationError,
    RunManifest,
    RunStatus,
    StageStatus,
    atomic_write_json,
    hash_file,
    validate_manifest,
)
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config


def test_manifest_record_serializes_minimal_inventory(tmp_path: Path) -> None:
    data_path = tmp_path / "data" / "prices.csv"
    data_path.parent.mkdir()
    data_path.write_text("price\n1\n")

    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={"schema_version": 1},
    )
    manifest.add_stage("data", StageStatus.COMPLETED)
    manifest.add_artifact(
        artifact_id="data.prices",
        role="prices",
        artifact_type="table",
        producer_stage="data",
        path="data/prices.csv",
        content_hash=hash_file(data_path),
        size=data_path.stat().st_size,
        schema_version="prices.v1",
        status=ArtifactStatus.COMPLETED,
        upstream_artifact_ids=[],
        visibility=ArtifactVisibility.PUBLIC,
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == 2
    assert payload["run"]["id"] == "run-1"
    assert payload["run"]["run_dir"] == "run-1"
    assert str(tmp_path) not in json.dumps(payload)
    assert payload["run"]["status"] == RunStatus.RUNNING
    assert payload["stages"][0]["id"] == "data"
    assert payload["artifacts"][0]["id"] == "data.prices"
    validate_manifest(payload, run_dir=tmp_path)


def test_completed_artifact_requires_content_identity(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )

    with pytest.raises(ManifestValidationError, match="hash"):
        manifest.add_artifact(
            artifact_id="bad",
            role="report",
            artifact_type="json",
            producer_stage="report",
            path="report.json",
            content_hash="",
            size=10,
            schema_version="report.v1",
            status=ArtifactStatus.COMPLETED,
        )


def test_manifest_validation_rejects_missing_completed_artifact_file(tmp_path: Path) -> None:
    artifact_path = tmp_path / "report.json"
    artifact_path.write_text("{}\n")
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    manifest.add_artifact(
        artifact_id="report",
        role="report",
        artifact_type="json",
        producer_stage="report",
        path="report.json",
        content_hash=hash_file(artifact_path),
        size=artifact_path.stat().st_size,
        schema_version="report.v1",
        status=ArtifactStatus.COMPLETED,
    )
    artifact_path.unlink()

    with pytest.raises(ManifestValidationError, match="completed artifact is missing"):
        validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_manifest_rejects_duplicate_artifact_ids_and_paths(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    artifact = {
        "role": "report",
        "artifact_type": "json",
        "producer_stage": "report",
        "path": "report.json",
        "content_hash": "a" * 64,
        "size": 10,
        "schema_version": "report.v1",
        "status": ArtifactStatus.COMPLETED,
    }
    manifest.add_artifact(artifact_id="report", **artifact)

    with pytest.raises(ManifestValidationError, match="duplicate artifact id"):
        manifest.add_artifact(artifact_id="report", **{**artifact, "path": "report-2.json"})
    with pytest.raises(ManifestValidationError, match="duplicate artifact path"):
        manifest.add_artifact(artifact_id="report2", **artifact)


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/escape.json",
        "../escape.json",
        "nested/../../escape",
        "C:\\Users\\alice\\secret.pkl",
        "\\\\server\\share\\secret.pkl",
        "~/.cache/provider",
    ],
)
def test_manifest_rejects_unsafe_artifact_paths(tmp_path: Path, path: str) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )

    with pytest.raises(ManifestValidationError, match="run-relative"):
        manifest.add_artifact(
            artifact_id="unsafe",
            role="report",
            artifact_type="json",
            producer_stage="report",
            path=path,
            content_hash="a" * 64,
            size=10,
            schema_version="report.v1",
            status=ArtifactStatus.COMPLETED,
        )


def test_atomic_write_json_preserves_previous_file_on_serialization_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_json(target, {"valid": True})

    with pytest.raises(TypeError):
        atomic_write_json(target, {"invalid": {object()}})

    assert json.loads(target.read_text()) == {"valid": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_artifact_registry_completes_only_after_hash_and_manifest_update(
    tmp_path: Path,
) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    registry = ArtifactRegistry(manifest, tmp_path)
    artifact_path = tmp_path / "reports" / "survival_report.json"

    registry.plan_artifact(
        artifact_id="report.survival",
        role="survival_report",
        artifact_type="json",
        producer_stage="report",
        path="reports/survival_report.json",
        schema_version="survival_report.v1",
    )
    registry.begin_artifact_write("report.survival")
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("{}\n")

    with pytest.raises(ManifestValidationError, match="hash"):
        registry.complete_artifact("report.survival")

    registry.complete_artifact("report.survival", content_hash=hash_file(artifact_path))

    payload = manifest.to_dict()
    assert payload["artifacts"][0]["status"] == ArtifactStatus.COMPLETED
    validate_manifest(payload, run_dir=tmp_path)


def test_manifest_validation_rejects_completed_aggregate_with_incomplete_child(
    tmp_path: Path,
) -> None:
    aggregate = tmp_path / "aggregate.csv"
    aggregate.write_text("value\n1\n")
    child = tmp_path / "child.csv"
    child.write_text("value\n1\n")
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    manifest.add_artifact(
        artifact_id="child",
        role="child",
        artifact_type="csv",
        producer_stage="validation",
        path="child.csv",
        content_hash=hash_file(child),
        size=child.stat().st_size,
        schema_version="child.v1",
        status=ArtifactStatus.FAILED,
    )
    manifest.add_artifact(
        artifact_id="aggregate",
        role="aggregate",
        artifact_type="csv",
        producer_stage="validation",
        path="aggregate.csv",
        content_hash=hash_file(aggregate),
        size=aggregate.stat().st_size,
        schema_version="aggregate.v1",
        status=ArtifactStatus.COMPLETED,
        upstream_artifact_ids=["child"],
    )

    with pytest.raises(ManifestValidationError, match="incomplete upstream"):
        validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_environment_evidence_is_allowlist_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-capture")

    evidence = capture_environment_evidence()

    assert evidence["variables"]["LANG"] == "C.UTF-8"
    assert "do-not-capture" not in json.dumps(evidence)
    assert "AWS_SECRET_ACCESS_KEY" not in json.dumps(evidence)


def test_git_evidence_excludes_raw_diff() -> None:
    evidence = capture_git_evidence(Path.cwd())

    if evidence["available"]:
        assert "diff" not in evidence
        assert "diff_hash" in evidence
        assert "changed_files" in evidence


def test_git_evidence_includes_staged_and_untracked_content_identity(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(
        tmp_path,
        "-c",
        "user.name=Aegis",
        "-c",
        "user.email=aegis@example.test",
        "commit",
        "--allow-empty",
        "-m",
        "init",
    )
    clean = capture_git_evidence(tmp_path)

    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n")
    _git(tmp_path, "add", "tracked.txt")
    staged = capture_git_evidence(tmp_path)

    assert staged["dirty"] is True
    assert "tracked.txt" in staged["changed_files"]
    assert staged["diff_hash"] != clean["diff_hash"]

    untracked = tmp_path / "untracked.txt"
    untracked.write_text("one\n")
    first_untracked = capture_git_evidence(tmp_path)
    untracked.write_text("two\n")
    second_untracked = capture_git_evidence(tmp_path)

    assert "untracked.txt" in second_untracked["changed_files"]
    assert second_untracked["diff_hash"] != first_untracked["diff_hash"]


def test_run_start_evidence_uses_public_redacted_config_hashes(tmp_path: Path) -> None:
    config = build_resolved_run_config(tmp_path)

    evidence = capture_run_start_evidence(config, repo_path=Path.cwd())

    assert evidence["config"]["authored_config_hash"]
    assert evidence["config"]["resolved_config_hash"]
    assert evidence["config"]["raw_config_identity"]["visibility"] == ArtifactVisibility.PRIVATE
    assert evidence["environment"]["variables"] == capture_environment_evidence()["variables"]


def _git(repo_path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_path, check=True, capture_output=True)
