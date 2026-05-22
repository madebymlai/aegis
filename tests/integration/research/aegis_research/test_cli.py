from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)


def test_root_help_identifies_aerd(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0

    output = capsys.readouterr()
    assert "usage: aerd" in output.out
    assert "run" in output.out
    assert "show" in output.out
    assert "train" not in output.out
    assert "play" not in output.out
    assert "exp" not in output.out


def test_run_help_does_not_list_train_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--help"]) == 0

    output = capsys.readouterr()
    assert "--train" not in output.out
    assert "Run the config's train section" not in output.out


def test_show_splitters_from_rolling_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "splitters", "from_rolling", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["method"] == "from_rolling"
    assert payload["run_scoring_set_policy"] == "exactly_two_sets_first_selection_second_held_out"
    param_names = {param["name"] for param in payload["params"]}
    assert {"length", "split", "offset"}.issubset(param_names)


def test_show_splitters_marks_runtime_object_methods_unsupported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "splitters", "from_split_func", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["supported"] is False
    assert "split_func" in payload["required_internal_params"]


def test_show_splitters_lists_catalog_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "splitters", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "splitter_catalog.v1"
    assert payload["run_scoring_set_policy"] == "exactly_two_sets_first_selection_second_held_out"
    assert any(method["method"] == "from_rolling" for method in payload["methods"])


def test_show_components_lists_registry_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research/components/indicators/returns.py")
    write_strategy_component(tmp_path / "research/components/strategies/strategy.py")

    assert cli.main(["show", "components", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    strategy = payload["families"]["strategies"]["demo.strategy"]
    indicator = payload["families"]["indicators"]["demo.returns"]
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert payload["fingerprint"]
    assert strategy["signal_outputs"] == ["entries", "exits"]
    assert strategy["params"]["param_space"]["available"] is False
    assert indicator["outputs"] == ["returns"]


def test_show_splitters_unknown_method_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "splitters", "missing_method", "--json"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert payload["error"]["category"] == "config_validation"
    assert "missing_method" in payload["error"]["message"]


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


def test_run_requires_explicit_config_without_train_guidance(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["run", "--json"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "requires an explicit config" in payload["error"]["message"]
    assert "--train" not in payload["error"]["message"]


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--train", "config.yaml", "--json"],
        ["run", "config.yaml", "--train", "--json"],
    ],
)
def test_run_rejects_removed_train_flag(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(argv) == 2

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "invocation"
    assert "--train" in payload["error"]["message"]


def test_run_rejects_removed_labeler_without_train_guidance(
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
                "name": "bad_run",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 120,
                    "arrays": ["OHLCV"],
                },
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"id": "missing_strategy"},
                "labeler": {"id": "demo.fixlb"},
                "indicators": [{"id": "missing_indicator"}],
                "ranking": {"metric": "total_return", "direction": "desc"},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-run"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "training and lane fields are not supported" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-run").exists()


def test_run_rejects_stale_train_shaped_config_before_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "stale_train",
                "output_dir": "runs",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 120,
                    "arrays": ["OHLCV"],
                },
                "portfolio": {"entry_budget": 1.0},
                "labeler": {"id": "demo.fixlb"},
                "indicators": [{"id": "demo.returns"}],
                "train": {"model": {"source": "plugin", "id": "demo.model"}},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-mode"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "single run config contract" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-mode").exists()


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
