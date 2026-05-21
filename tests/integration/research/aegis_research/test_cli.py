from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_label_component,
)
from tests.support.research.aegis_research.model_plugin_fixtures import model_config_dict


def test_root_help_identifies_aerd(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0

    output = capsys.readouterr()
    assert "usage: aerd" in output.out
    assert "run" in output.out
    assert "play" not in output.out
    assert "train" not in output.out
    assert "exp" not in output.out


def test_package_metadata_exposes_aerd_script() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text())

    assert payload["project"]["scripts"] == {
        "aerd": "research.aegis_research.cli:main",
    }


@pytest.mark.parametrize("argv", [["nope", "--json"], ["--json", "nope"]])
def test_json_invocation_error_is_structured(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(argv) == 2

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert payload["error"]["category"] == "invocation"


def test_default_run_reports_strategy_labeler_conflict_without_train_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "lane": "run",
                "name": "bad_run",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 120,
                    "arrays": ["OHLCV"],
                },
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": "playbook", "id": "missing_strategy"},
                "labeler": {"id": "demo.fixlb"},
                "indicators": [{"source": "playbook", "ids": ["missing_indicator"]}],
                "ranking": {"metric": "total_return", "direction": "desc"},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-run"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "mutually exclusive" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-run").exists()


def test_default_run_guides_top_level_labeler_train_config_to_train_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-mode"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "aerd run --train" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-mode").exists()


def test_train_json_executes_valid_config_and_rejected_verdict_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path, report={"min_oos_sharpe": 999.0})

    assert cli.main(["run", "--train", str(config_path), "--json", "--run-id", "cli-json-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["lane"] == "train"
    assert payload["selection"]["source"] == "explicit"
    assert payload["run"]["id"] == "cli-json-run"
    assert payload["run"]["status"] == RunStatus.COMPLETED
    assert payload["report"]["status"] == "rejected"


def test_json_post_manifest_failure_includes_safe_run_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REMOTE_PASSWORD", "hunter2")
    config_path = _write_config(
        tmp_path,
        data={
            "source": "yf",
            "symbols": ["SYN"],
            "start": "2020-01-01",
            "end": "2021-01-01",
            "timeframe": "1D",
            "provider_kwargs": {"password": {"env": "REMOTE_PASSWORD"}},
        },
    )

    def fail_after_manifest(_config, **_kwargs):
        assert (tmp_path / "runs" / "post-manifest" / "manifest.json").exists()
        raise OSError("provider returned hunter2")

    monkeypatch.setattr(
        "research.aegis_research.experiments.load_market_data_result",
        fail_after_manifest,
    )

    assert (
        cli.main(["run", "--train", str(config_path), "--json", "--run-id", "post-manifest"]) == 10
    )

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "execution_failure"
    assert payload["run"]["id"] == "post-manifest"
    assert payload["run"]["status"] == RunStatus.FAILED
    assert payload["run"]["manifest_path"] == "runs/post-manifest/manifest.json"
    assert "hunter2" not in output.err


def test_top_level_keyboard_interrupt_json_is_structured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_parser", interrupt)

    assert cli.main(["--json"]) == 130

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "interrupted"


def test_train_keyboard_interrupt_json_preserves_run_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    def interrupt_run(_config, **kwargs):
        kwargs["on_run_started"](
            {
                "run_id": "interrupted-run",
                "run_dir": str(tmp_path / "runs" / "interrupted-run"),
                "manifest_path": str(tmp_path / "runs" / "interrupted-run" / "manifest.json"),
                "status": "interrupted",
            }
        )
        raise KeyboardInterrupt

    monkeypatch.setattr("research.aegis_research.cli_commands.run.run_training", interrupt_run)

    assert (
        cli.main(["run", "--train", str(config_path), "--json", "--run-id", "interrupted-run"])
        == 130
    )

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "interrupted"
    assert payload["run"]["id"] == "interrupted-run"


def test_train_records_explicit_config_selection_in_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)

    assert (
        cli.main(["run", "--train", str(config_path), "--json", "--run-id", "selection-run"]) == 0
    )

    capsys.readouterr()
    manifest = json.loads((tmp_path / "runs" / "selection-run" / "manifest.json").read_text())
    assert manifest["config"]["selection"] == {
        "source": "explicit",
        "config_path": "experiment.yaml",
    }


def test_output_helper_normalizes_nonstandard_json_numbers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from research.aegis_research.cli_support.output import CommandResult, write_success

    assert (
        write_success(
            CommandResult(command="test", payload={"value": float("nan")}),
            json_mode=True,
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out)["value"] is None


def test_safe_path_hides_relative_paths_that_escape_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research.aegis_research.cli_support.output import safe_path

    worktree = tmp_path / "repo"
    worktree.mkdir()
    monkeypatch.chdir(worktree)

    assert safe_path("runs/example") == "runs/example"
    assert safe_path("../private/runs") == "<path>"


def _write_config(tmp_path: Path, **overrides: Any) -> Path:
    write_label_component(tmp_path / "research/components/labels/fixlb.py")
    write_indicator_component(tmp_path / "research/components/indicators/returns.py")
    model = model_config_dict(min_train_samples=1)
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "cli_contract",
        "output_dir": "runs",
        "data": {
            "source": "synthetic",
            "symbols": ["SYN"],
            "rows": 120,
            "timeframe": "1D",
            "arrays": ["OHLCV"],
        },
        "portfolio": {"entry_budget": 1.0},
        "report": {"freq": "1D", "year_freq": "252D"},
        "labeler": {"id": "demo.fixlb"},
        "indicators": [{"source": "component", "ids": ["demo.returns"]}],
        "train": {
            "model": {
                "source": "plugin",
                "id": model["plugin_id"],
                "min_train_samples": model["min_train_samples"],
                "params": model["params"],
            },
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path
