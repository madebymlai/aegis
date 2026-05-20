from __future__ import annotations

import json
from pathlib import Path

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
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
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
    assert artifact["strategy"]["consumes_runner_data"] is True
    assert artifact["strategy"]["data_binding"] == "strategy_inputs"
    assert artifact["data"]["strategy_consumed_runner_data"] is True
    assert artifact["data"]["strategy_data_binding"] == "strategy_inputs"
    assert artifact["indicators"][0]["source"] == "playbook"
    assert artifact["indicators"][0]["id"] == "ma_explore"
    assert artifact["leaderboard"]["summary"]["succeeded"] == 1
    assert artifact["leaderboard"]["rows"][0]["strategy_source"] == "playbook"
    assert artifact["leaderboard"]["rows"][0]["metric_authority"] == "aegis"


def test_run_cli_expands_all_playbook_indicators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_one.py", "indicators", "ma_one")
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_two.py", "indicators", "ma_two")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        indicators=[{"source": "playbook", "ids": "all"}],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "playbook-all-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    artifact = json.loads(
        (tmp_path / "runs" / "playbook-all-run" / "strategy_run.json").read_text()
    )
    assert [item["id"] for item in artifact["indicators"]] == ["ma_one", "ma_two"]


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


def test_run_cli_rejects_duplicate_expanded_playbook_indicators_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(tmp_path / "research/playbooks/indicators/ma_one.py", "indicators", "ma_one")
    config_path = _write_run_config(
        tmp_path,
        strategy_source="playbook",
        strategy_id="ma_cross",
        indicators=[
            {"source": "playbook", "ids": "all"},
            {"source": "playbook", "ids": ["ma_one"]},
        ],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "duplicate-playbook"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "duplicate expanded playbook indicator id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "duplicate-playbook").exists()


def test_run_cli_reports_failed_playbook_execution_on_run_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_failing_playbook(tmp_path / "research/playbooks/strategies/bad.py", "strategies", "bad")
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="bad")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "failed-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "failed-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert payload["run"]["status"] == RunStatus.FAILED
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_playbook_variant_without_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py", "strategies", "ma_cross"
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py",
        "indicators",
        "ma_explore",
        include_params=False,
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "missing-params"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "missing-params" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "params must be a mapping" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_strategy_playbook_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/ma_cross.py",
        "strategies",
        "ma_cross",
        include_metrics=True,
    )
    _write_playbook(
        tmp_path / "research/playbooks/indicators/ma_explore.py", "indicators", "ma_explore"
    )
    config_path = _write_run_config(tmp_path, strategy_source="playbook", strategy_id="ma_cross")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "metric-playbook"]) == 10

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "metric-playbook" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert "metric or portfolio fields" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED


def test_run_cli_rejects_playbook_that_does_not_support_requested_family(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_playbook(
        tmp_path / "research/playbooks/strategies/labels_only.py",
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
                f"research/playbooks/{family}/local.py",
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
    indicators: list[dict[str, object]] | None = None,
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "run_playbook_source_test",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 80,
                    "arrays": ["OHLCV"],
                },
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": strategy_source, "id": strategy_id},
                "indicators": indicators
                if indicators is not None
                else [{"source": "playbook", "ids": ["ma_explore"]}],
                "ranking": {"metric": "total_return_pct", "direction": "desc"},
            },
            sort_keys=False,
        )
    )
    return path


def _write_playbook(
    path: Path,
    family: str,
    playbook_id: str,
    *,
    stages: list[str] | None = None,
    include_params: bool = True,
    include_metrics: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": stages or [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    if family == "indicators":
        manifest["indicator_family"] = "ma"
    params_source = "'params': {'window': 5}, " if include_params else ""
    if family == "strategies":
        metrics_source = "'metrics': {'total_return_pct': 1.5}, " if include_metrics else ""
        body = (
            "def run(inputs):\n"
            '    """Generate moving-average crossover candidates for central scoring."""\n'
            "    close = inputs.data.feature('Close')\n"
            "    average = close.rolling(3).mean()\n"
            "    return {'variant_records': [{'variant_id': "
            f"{playbook_id!r}, {params_source}"
            f"{metrics_source}"
            "'entries': (close > average).fillna(False), "
            "'exits': (close < average).fillna(False)}]}\n"
        )
    else:
        body = (
            "def run(_inputs):\n"
            '    """Return fixture variant params for playbook source tests."""\n'
            "    return {'variant_records': [{'variant_id': "
            f"{playbook_id!r}, {params_source}"
            "}]}\n"
        )
    path.write_text(
        "# %% playbook overview\n"
        "# Integration fixture playbook selected by stable ID.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n" + body
    )


def _write_failing_playbook(path: Path, family: str, playbook_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": family,
        "id": playbook_id,
        "version": "1.0.0",
        "stages": [family],
        "accepted_inputs": ["Close"],
        "result_schema": "playbook_result.v1",
    }
    path.write_text(
        "# %% playbook overview\n"
        "# Integration fixture playbook that fails during callable execution.\n"
        "# Source: synthetic Close data supplied by run config.\n"
        "\n"
        "# %% define playbook metadata\n"
        f"PLAYBOOK_MANIFEST = {manifest!r}\n"
        "PLAYBOOK_CALLABLE = 'run'\n"
        "\n"
        "# %% main compute\n"
        "def run(_inputs):\n"
        '    """Raise a deterministic fixture error for failure-path tests."""\n'
        "    raise RuntimeError('boom token=secret')\n"
    )
