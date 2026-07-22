from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research.aegis_research.atomic_write import hash_file
from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.provenance.artifacts import ArtifactRegistry
from research.aegis_research.provenance.capture import (
    canonical_hash,
    capture_environment_evidence,
    capture_git_evidence,
    capture_run_start_evidence,
)
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ManifestValidationError,
    RunManifest,
    RunStatus,
    StageStatus,
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
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == 4
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


def test_canonical_hash_is_deterministic_for_normal_payload() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == (
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    )


def test_canonical_hash_serializes_non_finite_values_as_null() -> None:
    payload = {"value": float("nan")}

    assert canonical_json_bytes(payload) == b'{"value":null}'
    assert canonical_hash(payload) == (
        "1c197daef20de3f47eec5e2f735ec6669869d3180cc29f35be4788511e0af0f8"
    )


def test_artifact_registry_requires_the_persist_hook(tmp_path: Path) -> None:
    # Durability is not optional: a registry that cannot persist the manifest
    # must be unconstructable, not silently in-memory-only.
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )

    with pytest.raises(TypeError, match="persist"):
        ArtifactRegistry(manifest, tmp_path)


def test_artifact_registry_persists_the_manifest_on_every_mutation(
    tmp_path: Path,
) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    persist_calls: list[bool] = []
    registry = ArtifactRegistry(manifest, tmp_path, persist=lambda: persist_calls.append(True))
    artifact_path = tmp_path / "report.json"

    registry.plan_artifact(
        artifact_id="report.survival",
        role="survival_report",
        artifact_type="json",
        producer_stage="report",
        path="report.json",
        schema_version="survival_report.v1",
    )
    assert len(persist_calls) == 1

    registry.begin_artifact_write("report.survival")
    assert len(persist_calls) == 2

    artifact_path.write_text("{}\n")
    registry.complete_artifact("report.survival", content_hash=hash_file(artifact_path))
    assert len(persist_calls) == 3


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
    registry = ArtifactRegistry(manifest, tmp_path, persist=lambda: None)
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


def test_run_start_evidence_hashes_raw_config(tmp_path: Path) -> None:
    from research.aegis_research.canonical_json import to_builtin

    config = build_resolved_run_config(tmp_path)

    evidence = capture_run_start_evidence(config, repo_path=Path.cwd())

    assert evidence["config"]["authored_config_hash"] == canonical_hash(config.authored_config)
    assert evidence["config"]["resolved_config_hash"] == canonical_hash(to_builtin(config.config))
    assert "visibility" not in evidence["config"]["raw_config_identity"]
    assert evidence["environment"]["variables"] == capture_environment_evidence()["variables"]


def _git(repo_path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_path, check=True, capture_output=True)
