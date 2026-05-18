from __future__ import annotations

import json
from pathlib import Path

import nbformat
import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION


def test_play_cli_executes_repo_controlled_playbook_by_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_notebook(tmp_path / "research/playbooks/indicators/ma_explore.ipynb", "ma_explore")
    config_path = _write_play_config(tmp_path, "ma_explore")

    assert cli.main(["play", str(config_path), "--json"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["lane"] == "play"
    assert payload["playbooks"][0]["id"] == "ma_explore"
    assert payload["results"][0]["variant_records"] == [{"id": "ma_explore", "window": 5}]


def test_play_cli_unknown_playbook_fails_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_play_config(tmp_path, "missing")

    assert cli.main(["play", str(config_path), "--json"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert "unknown playbook id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "play").exists()


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


def _write_play_config(tmp_path: Path, playbook_id: str) -> Path:
    path = tmp_path / "play.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "lane": "play",
                "name": "play_cli_test",
                "portfolio": {"entry_budget": 1.0},
                "play": {
                    "stages": ["indicators"],
                    "indicator_refs": [
                        {"source": "playbook", "id": playbook_id, "params": {"window": 5}}
                    ],
                    "ranking": {"metric": "total_return_pct", "direction": "desc"},
                },
            },
            sort_keys=False,
        )
    )
    return path


def _write_notebook(path: Path, playbook_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook(
        metadata={
            "aegis_playbook": {
                "family": "indicators",
                "id": playbook_id,
                "version": "1.0.0",
                "stages": ["indicators"],
                "accepted_inputs": ["close"],
                "indicator_family": "ma",
                "result_schema": "playbook_result.v1",
            }
        },
        cells=[
            nbformat.v4.new_code_cell(
                "AEGIS_PLAYBOOK_RESULT = {"
                "'variant_records': [{'id': '"
                + playbook_id
                + "', 'window': AEGIS_PLAYBOOK_PARAMS['window']}]}"
            )
        ],
    )
    nbformat.write(nb, path)
