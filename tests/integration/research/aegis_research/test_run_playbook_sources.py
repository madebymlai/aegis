from __future__ import annotations

import json
from pathlib import Path

import nbformat
import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus


def test_run_cli_executes_repo_controlled_playbooks_by_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_notebook(tmp_path / "research/playbooks/strategies/ma_cross.ipynb", "strategies", "ma_cross")
    _write_notebook(tmp_path / "research/playbooks/indicators/ma_explore.ipynb", "indicators", "ma_explore")
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "playbook-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    artifact = json.loads((tmp_path / "runs" / "playbook-run" / "strategy_run.json").read_text())
    assert payload["status"] == "success"
    assert payload["lane"] == "run"
    assert artifact["strategy"]["source"] == "playbook"
    assert artifact["strategy"]["id"] == "ma_cross"
    assert artifact["indicators"][0]["source"] == "playbook"
    assert artifact["indicators"][0]["id"] == "ma_explore"
    assert artifact["leaderboard"]["summary"]["succeeded"] == 2
    assert artifact["leaderboard"]["rows"][0]["indicator_source"] in {None, "playbook"}


def test_run_cli_unknown_playbook_fails_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="missing")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert "unknown playbook id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_run_cli_reports_failed_playbook_execution_on_run_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_failing_notebook(tmp_path / "research/playbooks/strategies/bad.ipynb", "strategies", "bad")
    _write_notebook(tmp_path / "research/playbooks/indicators/ma_explore.ipynb", "indicators", "ma_explore")
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="bad")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "failed-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "failed-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert payload["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_playbook_that_does_not_support_requested_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_notebook(
        tmp_path / "research/playbooks/strategies/labels_only.ipynb",
        "strategies",
        "labels_only",
        stages=["labels"],
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="labels_only")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "does not support strategies" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_playbook_roots_ignore_local_notebooks_except_readme_placeholders() -> None:
    for family in ("labels", "indicators", "strategies"):
        assert Path(f"research/playbooks/{family}/README.md").is_file()
        ignored_notebook = pytest.importorskip("subprocess").run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/playbooks/{family}/local.ipynb",
            ],
            check=False,
        )
        ignored_readme = pytest.importorskip("subprocess").run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "--quiet",
                f"research/playbooks/{family}/README.md",
            ],
            check=False,
        )

        assert ignored_notebook.returncode == 0
        assert ignored_readme.returncode == 1


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_source: str,
    strategy_id: str,
    indicator_refs: list[dict[str, object]] | None = None,
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "lane": "run",
                "name": "run_playbook_source_test",
                "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 80},
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": strategy_source, "id": strategy_id, "params": {"window": 5}},
                "indicator_refs": indicator_refs
                if indicator_refs is not None
                else [{"source": "playbook", "id": "ma_explore", "params": {"window": 5}}],
                "ranking": {"metric": "total_return_pct", "direction": "desc"},
            },
            sort_keys=False,
        )
    )
    return path


def _write_notebook(
    path: Path,
    family: str,
    playbook_id: str,
    *,
    stages: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": stages or [family],
        "accepted_inputs": ["close"],
        "result_schema": "playbook_result.v1",
    }
    if family == "indicators":
        metadata["indicator_family"] = "ma"
    nb = nbformat.v4.new_notebook(
        metadata={"aegis_playbook": metadata},
        cells=[
            nbformat.v4.new_code_cell(
                "AEGIS_PLAYBOOK_RESULT = {"
                "'variant_records': [{'variant_id': '"
                + playbook_id
                + "', 'params': AEGIS_PLAYBOOK_PARAMS, "
                "'metrics': {'total_return_pct': 1.5}}]}"
            )
        ],
    )
    nbformat.write(nb, path)


def _write_failing_notebook(path: Path, family: str, playbook_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": [family],
        "accepted_inputs": ["close"],
        "result_schema": "playbook_result.v1",
    }
    nb = nbformat.v4.new_notebook(
        metadata={"aegis_playbook": metadata},
        cells=[nbformat.v4.new_code_cell("raise RuntimeError('boom token=secret')")],
    )
    nbformat.write(nb, path)
