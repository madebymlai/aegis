from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.cli_support.defaults import default_store
from research.aegis_research.config import CONFIG_SCHEMA_VERSION, ResolvedExperimentConfig
from tests.support.research.aegis_research.model_plugin_fixtures import model_config_dict


def test_defaults_set_json_persists_git_local_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    config_path = _write_config(repo / "experiment.yaml")
    monkeypatch.chdir(repo)

    assert cli.main(["exp", "defaults", "set", str(config_path), "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert output.err == ""
    assert payload["selection"] == {
        "source": "local_default",
        "config_path": "experiment.yaml",
    }
    state = json.loads(default_store().state_path.read_text())
    assert state["selected_config"] == "experiment.yaml"
    assert "provider_kwargs" not in json.dumps(state)


def test_run_uses_default_from_nested_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    config_path = _write_config(repo / "experiment.yaml")
    nested = repo / "nested" / "dir"
    nested.mkdir(parents=True)
    monkeypatch.chdir(repo)
    assert cli.main(["exp", "defaults", "set", str(config_path)]) == 0
    capsys.readouterr()

    captured: dict[str, Any] = {}

    def fake_run(config, **kwargs):
        captured["config"] = config
        return _fake_run_result(nested, kwargs.get("run_id") or "default-run")

    monkeypatch.setattr("research.aegis_research.cli_commands.run.run_experiment", fake_run)
    monkeypatch.chdir(nested)

    assert cli.main(["run", "--json", "--run-id", "default-run"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    resolved = captured["config"]
    assert isinstance(resolved, ResolvedExperimentConfig)
    assert resolved.selection is not None
    assert resolved.selection.source == "local_default"
    assert resolved.selection.config_path == "experiment.yaml"
    assert payload["selection"]["source"] == "local_default"


def test_default_backed_run_records_selection_in_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    config_path = _write_config(repo / "experiment.yaml")
    monkeypatch.chdir(repo)
    assert cli.main(["exp", "defaults", "set", str(config_path)]) == 0
    capsys.readouterr()

    assert cli.main(["run", "--json", "--run-id", "default-selection-run"]) == 0
    capsys.readouterr()

    manifest = json.loads((repo / "runs" / "default-selection-run" / "manifest.json").read_text())
    assert manifest["config"]["selection"] == {
        "source": "local_default",
        "config_path": "experiment.yaml",
    }


def test_explicit_config_ignores_stale_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    config_path = _write_config(repo / "experiment.yaml")
    monkeypatch.chdir(repo)
    state_path = default_store().state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"schema_version": 1, "selected_config": "missing.yaml"}) + "\n"
    )

    captured: dict[str, Any] = {}

    def fake_run(config, **kwargs):
        captured["config"] = config
        return _fake_run_result(repo, kwargs.get("run_id") or "explicit-run")

    monkeypatch.setattr("research.aegis_research.cli_commands.run.run_experiment", fake_run)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "explicit-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    resolved = captured["config"]
    assert isinstance(resolved, ResolvedExperimentConfig)
    assert resolved.selection is not None
    assert resolved.selection.source == "explicit"
    assert payload["selection"]["source"] == "explicit"


def test_missing_default_fails_before_run_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)

    assert cli.main(["run", "--json"]) == 3

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert output.out == ""
    assert payload["error"]["category"] == "missing_default"
    assert not (repo / "runs").exists()


def test_defaults_fail_outside_git_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path / "experiment.yaml")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["exp", "defaults", "set", str(config_path), "--json"]) == 4

    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["category"] == "default_resolution"


def test_defaults_set_malformed_config_is_config_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    config_path = repo / "malformed.yaml"
    config_path.write_text("name: [\n")
    monkeypatch.chdir(repo)

    assert cli.main(["exp", "defaults", "set", str(config_path), "--json"]) == 6

    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["category"] == "config_validation"


def test_invalid_default_selection_does_not_replace_prior_valid_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    valid_path = _write_config(repo / "valid.yaml")
    invalid_path = _write_config(
        repo / "invalid.yaml",
        model={**model_config_dict(), "plugin_id": "unknown.model"},
    )
    monkeypatch.chdir(repo)

    assert cli.main(["exp", "defaults", "set", str(valid_path)]) == 0
    capsys.readouterr()
    assert cli.main(["exp", "defaults", "set", str(invalid_path), "--json"]) == 6

    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["category"] == "config_validation"
    state = json.loads(default_store().state_path.read_text())
    assert state["selected_config"] == "valid.yaml"


def test_default_selection_outside_worktree_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _git_repo(tmp_path / "repo")
    outside_config = _write_config(tmp_path / "outside.yaml")
    monkeypatch.chdir(repo)

    assert cli.main(["exp", "defaults", "set", str(outside_config), "--json"]) == 4

    output = capsys.readouterr()
    assert json.loads(output.err)["error"]["category"] == "default_resolution"


def test_default_storage_is_isolated_per_git_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _git_repo(tmp_path / "first")
    second = _git_repo(tmp_path / "second")
    config_path = _write_config(first / "experiment.yaml")
    monkeypatch.chdir(first)
    assert cli.main(["exp", "defaults", "set", str(config_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(second)
    assert cli.main(["run", "--json"]) == 3
    assert json.loads(capsys.readouterr().err)["error"]["category"] == "missing_default"


@pytest.mark.parametrize(
    "state_text",
    [
        "not json",
        json.dumps({"schema_version": 99, "selected_config": "experiment.yaml"}),
        json.dumps({"schema_version": 1}),
        json.dumps({"schema_version": 1, "selected_config": "missing.yaml"}),
    ],
)
def test_corrupt_or_stale_default_state_fails_before_run_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    state_text: str,
) -> None:
    repo = _git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    state_path = default_store().state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state_text + "\n")

    assert cli.main(["run", "--json"]) == 4

    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"]["category"] == "default_resolution"
    assert not (repo / "runs").exists()


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    return path


def _write_config(path: Path, **overrides: Any) -> Path:
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": path.stem.replace("-", "_"),
        "output_dir": "runs",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "timeframe": "1D"},
        "model": model_config_dict(min_train_samples=1),
        "portfolio": {"entry_budget": 1.0},
        "report": {"freq": "1D", "year_freq": "252D"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _fake_run_result(base: Path, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_dir": str(base / "runs" / run_id),
        "manifest_path": str(base / "runs" / run_id / "manifest.json"),
        "status": "completed",
        "started_at": "2026-05-18T00:00:00Z",
        "finished_at": "2026-05-18T00:00:01Z",
        "report_artifact_id": "report.survival",
        "report": {"status": "survived", "reasons": ["ok"], "gate_outcomes": []},
    }
