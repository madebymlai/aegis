from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
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
    assert strategy["output_name"] == "active"
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
    assert "labeler: Unexpected keyword argument" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-run").exists()


def _signed_book_run_config(direction: str) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "directional_run",
        "output_dir": "runs",
        "data": {
            "source": "synthetic",
            "symbols": ["SYN"],
            "rows": 120,
            "arrays": ["OHLCV"],
        },
        "portfolio": {"gross_cap": 1.0, "direction": direction},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 40, "offset": 40, "split": 0.5},
                "max_splits": 2,
            },
        },
    }


def test_run_rejects_unknown_portfolio_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(_signed_book_run_config("sideways"), sort_keys=False)
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-dir"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "portfolio.direction" in payload["error"]["message"]


def test_run_accepts_shortonly_portfolio_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    write_strategy_component(tmp_path / "research" / "components" / "strategies" / "strategy.py")
    write_indicator_component(tmp_path / "research" / "components" / "indicators" / "returns.py")
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(_signed_book_run_config("shortonly"), sort_keys=False)
    )

    cli.main(["run", str(config_path), "--json", "--run-id", "short-dir"])

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "portfolio.direction" not in combined


def _carry_run_config(short_borrow_rate: float | None) -> dict[str, object]:
    config = _signed_book_run_config("both")
    config["name"] = "carry_run"
    if short_borrow_rate is not None:
        config["portfolio"]["short_borrow_rate"] = short_borrow_rate  # type: ignore[index]
        config["portfolio"]["short_rebate_rate"] = 0.0  # type: ignore[index]
    return config


def _run_candidate_returns(
    tmp_path: Path, short_borrow_rate: float | None, run_id: str
) -> list[object]:
    config_path = tmp_path / f"{run_id}.yaml"
    config_path.write_text(
        yaml.safe_dump(_carry_run_config(short_borrow_rate), sort_keys=False)
    )
    assert cli.main(["run", str(config_path), "--json", "--run-id", run_id]) == 0
    artifact = json.loads(
        (tmp_path / "runs" / run_id / "strategy_run.json").read_text()
    )
    return [candidate["metrics"]["total_return"] for candidate in artifact["candidates"]]


def test_run_long_only_strategy_returns_unchanged_whether_carry_on_or_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # End-to-end ADR-0007 guarantee: the demo strategy is long-only, so it has no short
    # legs to charge. Its candidate returns must be identical whether short borrow carry is
    # on at the non-zero default or explicitly switched off — carry never touches a long book.
    monkeypatch.chdir(tmp_path)
    write_strategy_component(tmp_path / "research" / "components" / "strategies" / "strategy.py")
    write_indicator_component(tmp_path / "research" / "components" / "indicators" / "returns.py")

    carry_on = _run_candidate_returns(tmp_path, short_borrow_rate=None, run_id="carry-on")
    carry_off = _run_candidate_returns(tmp_path, short_borrow_rate=0.0, run_id="carry-off")
    capsys.readouterr()

    assert carry_on == carry_off


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
    assert "Unexpected keyword argument" in payload["error"]["message"]
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


def test_held_out_summary_leads_with_held_out_and_gap_for_each_role() -> None:
    from research.aegis_research.cli_support.output import held_out_summary_lines

    def _summary(role: str, held_out: float, selection: float) -> dict[str, object]:
        return {
            "role": role,
            "held_out_headline": {
                "metric": "sharpe_ratio",
                "held_out": held_out,
                "selection": selection,
                "gap": selection - held_out,
            },
        }

    optimization = {
        "ranking_metric": "sharpe_ratio",
        "held_out_warning": "best candidate held-out sharpe_ratio +0.020 ...",
    }
    candidates = [
        _summary("best", 0.02, 1.97),
        _summary("median", -0.10, 1.20),
        _summary("worst", -0.30, 0.50),
    ]

    lines = held_out_summary_lines(optimization, candidates)

    text = "\n".join(lines)
    # Held-out is the headline column and precedes the in-sample column.
    header = next(line for line in lines if "held-out" in line and "in-sample" in line)
    assert header.index("held-out") < header.index("in-sample")
    assert "sharpe_ratio" in lines[0]
    # best/median/worst each surface held-out, in-sample, and the gap.
    assert "best" in text and "+0.020" in text and "+1.970" in text and "+1.950" in text
    assert "median" in text and "-0.100" in text
    assert "worst" in text and "-0.300" in text
    assert any(line.startswith("WARNING:") for line in lines)


def test_held_out_summary_is_empty_without_candidates() -> None:
    from research.aegis_research.cli_support.output import held_out_summary_lines

    assert held_out_summary_lines({"ranking_metric": "sharpe_ratio"}, []) == ()


def test_reproduce_lock_lines_emit_copy_paste_handles_and_footer() -> None:
    # aegis-rd-6ie: post-run output hands the user a copy-paste lock: handle per
    # representative candidate — best is the default role (bare), others carry :role —
    # plus a footer naming the run_id and the candidate-store path.
    from research.aegis_research.cli_support.output import reproduce_lock_lines

    run_id = "20260527T000603791760Z_etf_momentum"
    candidates = [{"role": "best"}, {"role": "median"}, {"role": "worst"}]

    lines = reproduce_lock_lines(
        run_id, candidates, store_path="runs/.candidate_store/candidates.sqlite3"
    )

    assert any(line.rstrip().endswith(f"lock: {run_id}") for line in lines)
    assert any(line.rstrip().endswith(f"lock: {run_id}:median") for line in lines)
    assert any(line.rstrip().endswith(f"lock: {run_id}:worst") for line in lines)
    assert any(line == f"run_id: {run_id}" for line in lines)
    assert any(line == "candidate store: runs/.candidate_store/candidates.sqlite3" for line in lines)


def test_reproduce_lock_lines_empty_without_candidates() -> None:
    from research.aegis_research.cli_support.output import reproduce_lock_lines

    assert reproduce_lock_lines("run-a", [], store_path="x") == ()


def _researched_optimization(
    *, total: int, excluded_invalid: int, excluded_degenerate: int
) -> dict[str, object]:
    return {
        "ranking_metric": "sharpe_ratio",
        "total": total,
        "excluded_invalid": excluded_invalid,
        "excluded_degenerate": excluded_degenerate,
    }


def _researched_candidate() -> dict[str, object]:
    return {
        "role": "best",
        "held_out_headline": {
            "metric": "sharpe_ratio",
            "held_out": 0.02,
            "selection": 1.97,
            "gap": 1.95,
        },
    }


def test_held_out_summary_renders_full_researched_ratio_when_nothing_excluded() -> None:
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        _researched_optimization(total=323, excluded_invalid=0, excluded_degenerate=0),
        [_researched_candidate()],
    )

    assert "researched candidates: 323/323" in lines
    assert not any("misconfigured" in line for line in lines)


def test_held_out_summary_subtracts_only_degenerate_from_total() -> None:
    from research.aegis_research.cli_support.output import held_out_summary_lines

    # researched = total - excluded_degenerate, computed from the exact total
    # (111 = 323 - 212), never a preflight estimate; invalid is a strict subset
    # of degenerate so it does not subtract twice.
    lines = held_out_summary_lines(
        _researched_optimization(total=323, excluded_invalid=0, excluded_degenerate=212),
        [_researched_candidate()],
    )

    assert "researched candidates: 111/323" in lines
    assert not any("misconfigured" in line for line in lines)


def test_held_out_summary_appends_misconfigured_clause_when_invalid_present() -> None:
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        _researched_optimization(total=323, excluded_invalid=2, excluded_degenerate=212),
        [_researched_candidate()],
    )

    assert "researched candidates: 111/323 (2 misconfigured)" in lines


def test_held_out_summary_no_held_rows_line_when_zero() -> None:
    """No non-executable rebalance rows line is rendered when the count is zero."""
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        {**_researched_optimization(total=30, excluded_invalid=0, excluded_degenerate=0),
         "non_executable_rows": 0},
        [_researched_candidate()],
    )

    assert not any("non-executable rebalance rows" in line for line in lines)


def test_held_out_summary_neutral_held_rows_line_for_purged_split() -> None:
    """A purged-split run with a positive count renders the neutral line."""
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        {**_researched_optimization(total=30, excluded_invalid=0, excluded_degenerate=0),
         "non_executable_rows": 7,
         "split_method": "from_purged_kfold"},
        [_researched_candidate()],
    )

    held_line = next(line for line in lines if "non-executable rebalance rows" in line)
    assert "non-executable rebalance rows: 7" in held_line
    assert "held at split seams" in held_line
    assert not held_line.startswith("WARNING")


def test_held_out_summary_warning_held_rows_line_for_contiguous_split() -> None:
    """A contiguous-split run with a positive count renders the WARNING-prefixed line."""
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        {**_researched_optimization(total=30, excluded_invalid=0, excluded_degenerate=0),
         "non_executable_rows": 3,
         "split_method": "from_rolling"},
        [_researched_candidate()],
    )

    held_line = next(line for line in lines if "non-executable rebalance rows" in line)
    assert held_line.startswith("WARNING:")
    assert "non-executable rebalance rows: 3" in held_line
    assert "should be zero" in held_line


def test_held_out_summary_held_rows_line_says_rebalance_rows_not_candidates() -> None:
    """The line wording references rebalance rows, not candidates."""
    from research.aegis_research.cli_support.output import held_out_summary_lines

    lines = held_out_summary_lines(
        {**_researched_optimization(total=30, excluded_invalid=0, excluded_degenerate=0),
         "non_executable_rows": 5,
         "split_method": "from_purged_kfold"},
        [_researched_candidate()],
    )

    held_line = next(line for line in lines if "non-executable rebalance rows" in line)
    assert "rebalance rows" in held_line
    assert "candidates" not in held_line.lower()


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


# ── config-schema show subcommand ────────────────────────────────────────────


def test_show_config_schema_exits_zero_and_prints_markdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human mode prints markdown with key contract sections."""
    assert cli.main(["show", "config-schema"]) == 0

    output = capsys.readouterr()
    guide = output.out

    assert "# Run Config Forward Contract" in guide
    assert "## Forward-Contract Overrides" in guide
    assert "## Top-Level Fields" in guide
    assert "## Literal Catalogs" in guide
    assert "## Split Parameters" in guide
    assert "## Component IDs" in guide
    assert "## Example Run Config" in guide

    # Prepass overlay: optimization required, schema_version const 8
    assert "optimization`** — required" in guide
    assert "schema_version`** — must be present and exactly `8`" in guide

    # Pointers to other show subcommands
    assert "`aerd show splitters <method>`" in guide
    assert "`aerd show components`" in guide


def test_show_config_schema_json_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON mode returns the standard structured envelope with full markdown."""
    assert cli.main(["show", "config-schema", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert payload["status"] == "success"
    assert payload["ok"] is True
    assert payload["command"] == "show"
    assert payload["format"] == "markdown"
    assert payload["schema_version"] == 1

    content = payload["content"]
    assert isinstance(content, str)
    assert len(content) > 1000  # Full guide, not clipped
    assert "# Run Config Forward Contract" in content
    assert "## Forward-Contract Overrides" in content
    assert "## Literal Catalogs" in content


def test_show_config_schema_marks_optimization_required_and_schema_version_const(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The rendered guide states the forward contract, not the raw model."""
    assert cli.main(["show", "config-schema"]) == 0

    guide = capsys.readouterr().out

    # optimization is marked required (model default is None)
    assert "optimization`** — required" in guide
    assert "forward contract requires" in guide.lower()

    # schema_version is const 8 (model default is CONFIG_SCHEMA_VERSION)
    assert "schema_version`** — must be present and exactly `8`" in guide


def test_show_config_schema_literal_catalogs_interpolated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Literal catalogs are interpolated from code constants at render time."""
    assert cli.main(["show", "config-schema"]) == 0

    guide = capsys.readouterr().out

    # Portfolio directions
    assert "Portfolio Directions" in guide
    assert "`longonly`" in guide
    assert "`shortonly`" in guide
    assert "`both`" in guide

    # Optimization search policies
    assert "Optimization Search Policies" in guide
    assert "`grid`" in guide
    assert "`random`" in guide

    # Data-array shortcuts
    assert "Data-Array Shortcuts" in guide
    assert "`OHLCV`" in guide

    # Lock roles
    assert "Lock Roles" in guide
    assert "`best`" in guide
    assert "`median`" in guide
    assert "`worst`" in guide

    # Signal catalogs
    assert "Signal Policies" in guide
    assert "Signal Execution Timings" in guide

    # Reserved execute keys
    assert "Reserved `optimization.execute` Keys" in guide


def test_show_config_schema_points_at_splitters_and_components(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide points at aerd show splitters and aerd show components."""
    assert cli.main(["show", "config-schema"]) == 0

    guide = capsys.readouterr().out

    assert "`aerd show splitters <method>`" in guide
    assert "`aerd show components`" in guide


def test_show_config_schema_embedded_example_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The embedded example Run Config YAML validates through the real
    validation coordinator with wired demo components."""
    monkeypatch.chdir(tmp_path)
    write_indicator_component(
        tmp_path / "research" / "components" / "indicators" / "returns.py"
    )
    write_strategy_component(
        tmp_path / "research" / "components" / "strategies" / "strategy.py"
    )

    from research.aegis_research.configuration import (
        CONFIG_SCHEMA_VERSION,
        resolve_run_config,
    )

    example_raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "example.run",
        "data": {
            "source": "synthetic",
            "symbols": ["A", "B", "C"],
            "rows": 250,
            "arrays": ["OHLCV"],
        },
        "portfolio": {
            "gross_cap": 1.0,
            "direction": "longonly",
        },
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "sharpe_ratio"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 126, "split": 0.5},
                "max_splits": 2,
            },
        },
    }

    resolved = resolve_run_config(example_raw)
    assert resolved is not None
    assert resolved.config.name == "example.run"
    assert resolved.config.data.source == "synthetic"
    assert resolved.config.portfolio.direction == "longonly"
    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "grid"


def test_show_config_schema_coherence_optimization_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Coherence: a config omitting optimization fails validation AND the
    rendered guide states it required."""
    # Side A: guide states optimization required
    assert cli.main(["show", "config-schema"]) == 0
    guide = capsys.readouterr().out
    assert "optimization`** — required" in guide

    # Side B: config omitting optimization fails validation
    monkeypatch.chdir(tmp_path)
    write_indicator_component(
        tmp_path / "research" / "components" / "indicators" / "returns.py"
    )
    write_strategy_component(
        tmp_path / "research" / "components" / "strategies" / "strategy.py"
    )

    from research.aegis_research.configuration import (
        CONFIG_SCHEMA_VERSION,
        ConfigValidationError,
        resolve_run_config,
    )

    raw_no_optimization = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "test",
        "data": {"source": "synthetic", "symbols": ["A"], "rows": 100, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "sharpe_ratio"},
    }

    with pytest.raises(ConfigValidationError) as exc_info:
        resolve_run_config(raw_no_optimization)

    messages = "; ".join(i.message for i in exc_info.value.issues)
    assert "optimization" in messages.lower()


# ── indicator-schema ────────────────────────────────────────────────────────


def test_show_indicator_schema_exits_zero_and_prints_markdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "indicator-schema"]) == 0

    output = capsys.readouterr()
    markdown = output.out

    # Title and key sections
    assert "# Indicator Component Authoring Guide" in markdown
    assert "## Percent-Cell Structure" in markdown
    assert "## Manifest" in markdown
    assert "## Entry Points" in markdown
    assert "## The `run` Entry Point" in markdown
    assert "## Optional `param_space`" in markdown
    assert "## Batch-Invariance Rule" in markdown
    assert "## Legacy Declarations" in markdown
    assert "## Complete Example" in markdown

    # v2 contract = run entry point (not legacy callable)
    assert "`run`" in markdown
    # Batched signature
    assert "n_candidates" in markdown
    # Mapping return contract
    assert 'return {"ma": result}' in markdown or 'return {"ma":' in markdown
    # Candidate-major layout
    assert "candidate_index * n_symbols" in markdown
    # Legacy keys are documented as hard errors
    assert "COMPONENT_CALLABLE" in markdown
    assert "wide_callable" in markdown
    assert "param_space_callable" in markdown


def test_show_indicator_schema_json_returns_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "indicator-schema", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["format"] == "markdown"
    assert payload["schema_version"] == "indicator_schema_guide.v1"
    assert "# Indicator Component Authoring Guide" in payload["content"]


def test_show_indicator_schema_manifest_table_is_interpolated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The manifest field table is interpolated from the pydantic model, not hand-written."""
    assert cli.main(["show", "indicator-schema"]) == 0

    markdown = capsys.readouterr().out

    # Field table has the Indicator-specific output_names field
    assert "| `output_names` |" in markdown
    assert "| `family` |" in markdown
    assert "| `id` |" in markdown
    assert "| `version` |" in markdown
    assert "| `input_names` |" in markdown
    assert "| `param_names` |" in markdown
    assert "| `defaults` |" in markdown
    assert "| `bar_aligned` |" in markdown


def test_show_indicator_schema_entrypoint_names_from_constants(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Entry-point names come from code constants, not hand-written strings."""
    from research.aegis_research.component_registry.contracts import (
        COMPONENT_ENTRYPOINT,
        COMPONENT_PARAM_SPACE_ENTRYPOINT,
    )

    assert cli.main(["show", "indicator-schema"]) == 0

    markdown = capsys.readouterr().out
    # The entry point name "run" appears in the guide (from COMPONENT_ENTRYPOINT)
    assert f"`{COMPONENT_ENTRYPOINT}` Entry Point" in markdown
    # The param space entry point name appears (from COMPONENT_PARAM_SPACE_ENTRYPOINT)
    assert f"Optional `{COMPONENT_PARAM_SPACE_ENTRYPOINT}`" in markdown


def test_show_indicator_schema_example_round_trips_through_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The packaged indicator example round-trips through the real registry parser/discovery."""
    # Copy the example into a fake component root
    import shutil

    from research.aegis_research.component_registry.contracts import (
        ComponentSelection,
        IndicatorManifest,
    )
    from research.aegis_research.component_registry.registry import (
        discover_component_registry,
    )
    example_src = Path(
        "research/aegis_research/component_registry/indicator_example.py"
    )
    dest = tmp_path / "research" / "components" / "indicators" / "example_ma.py"
    dest.parent.mkdir(parents=True)
    shutil.copy(example_src, dest)

    monkeypatch.chdir(tmp_path)
    registry = discover_component_registry(
        root=tmp_path / "research" / "components",
        repo_root=tmp_path,
    )

    assert registry.ids("indicators") == ("example.ma",)
    definition = registry.get(ComponentSelection("indicators", "example.ma"))
    manifest = definition.manifest
    assert isinstance(manifest, IndicatorManifest)
    assert manifest.id == "example.ma"
    assert manifest.version == "1.0.0"
    assert manifest.input_names == ("Close",)
    assert manifest.param_names == ("window", "wtype")
    assert manifest.output_names == ("ma",)
    assert manifest.defaults == {"window": 20, "wtype": "simple"}
    assert definition.has_param_space is True


def test_show_indicator_schema_guide_embeds_example_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide embeds the complete example source under ## Complete Example."""
    assert cli.main(["show", "indicator-schema"]) == 0

    markdown = capsys.readouterr().out
    # The example source is embedded as a code block
    assert "## Complete Example" in markdown
    # Key lines from the example
    assert 'COMPONENT_MANIFEST = {' in markdown
    assert '"family": "indicators"' in markdown
    assert '"id": "example.ma"' in markdown
    assert "def run(data, *, n_candidates, **param_lists):" in markdown


def test_show_components_unchanged_after_indicator_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`aerd show components` behavior is unchanged."""
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research/components/indicators/returns.py")
    write_strategy_component(tmp_path / "research/components/strategies/strategy.py")

    assert cli.main(["show", "components", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert "fingerprint" in payload
    assert "families" in payload


def test_show_splitters_catalog_unchanged_after_indicator_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`aerd show splitters` behavior is unchanged."""
    assert cli.main(["show", "splitters", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "splitter_catalog.v1"
    assert any(method["method"] == "from_rolling" for method in payload["methods"])


# ── strategy-schema ─────────────────────────────────────────────────────────


def test_show_strategy_schema_exits_zero_and_prints_markdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out

    # Title and key sections
    assert "# Strategy Component Authoring Guide" in markdown
    assert "## Percent-Cell Structure" in markdown
    assert "## Manifest" in markdown
    assert "## Entry Points" in markdown
    assert "## The `run` Entry Point" in markdown
    assert "## Optional `param_space`" in markdown
    assert "## NaN-Selection Convention" in markdown
    assert "## Ownership Boundaries" in markdown
    assert "## Batch-Invariance Rule" in markdown
    assert "## Legacy Declarations" in markdown
    assert "## Complete Example" in markdown

    # v2 contract = run entry point (not legacy callable)
    assert "`run`" in markdown
    # Batched signature with inputs object
    assert "n_candidates" in markdown
    assert "`inputs`" in markdown
    # Bare allocation-array return
    assert "bare" in markdown.lower()
    # consumes_outputs wiring
    assert "consumes_outputs" in markdown
    # Allocation-output catalog interpolated
    assert "`active`" in markdown
    assert "`target_weights`" in markdown
    # Ownership boundaries
    assert "portfolio.gross_cap" in markdown
    assert "owns_portfolio" in markdown
    # NaN-selection convention
    assert "NaN" in markdown
    assert "np.nan" in markdown
    # Legacy keys are documented as hard errors
    assert "COMPONENT_CALLABLE" in markdown
    assert "wide_callable" in markdown
    assert "param_space_callable" in markdown


def test_show_strategy_schema_json_returns_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "strategy-schema", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["format"] == "markdown"
    assert payload["schema_version"] == "strategy_schema_guide.v1"
    assert "# Strategy Component Authoring Guide" in payload["content"]


def test_show_strategy_schema_allocation_outputs_interpolated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The allocation-output catalog is interpolated from the registered constant."""
    from research.aegis_research.component_registry.contracts import (
        STRATEGY_ALLOCATION_OUTPUTS,
    )

    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out
    for output_name in sorted(STRATEGY_ALLOCATION_OUTPUTS):
        assert f"`{output_name}`" in markdown


def test_show_strategy_schema_manifest_table_is_interpolated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The manifest field table includes strategy-specific fields."""
    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out

    # Field table has the Strategy-specific fields
    assert "| `output_name` |" in markdown
    assert "| `consumes_outputs` |" in markdown
    assert "| `owns_portfolio` |" in markdown
    # Common base fields present
    assert "| `family` |" in markdown
    assert "| `id` |" in markdown
    assert "| `version` |" in markdown
    assert "| `input_names` |" in markdown
    assert "| `param_names` |" in markdown
    assert "| `defaults` |" in markdown


def test_show_strategy_schema_entrypoint_names_from_constants(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Entry-point names come from code constants, not hand-written strings."""
    from research.aegis_research.component_registry.contracts import (
        COMPONENT_ENTRYPOINT,
        COMPONENT_PARAM_SPACE_ENTRYPOINT,
    )

    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out
    # The entry point name "run" appears in the guide (from COMPONENT_ENTRYPOINT)
    assert f"`{COMPONENT_ENTRYPOINT}` Entry Point" in markdown
    # The param space entry point name appears (from COMPONENT_PARAM_SPACE_ENTRYPOINT)
    assert f"Optional `{COMPONENT_PARAM_SPACE_ENTRYPOINT}`" in markdown


def test_show_strategy_schema_example_round_trips_through_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The packaged strategy example round-trips through the real registry parser/discovery."""
    import shutil

    from research.aegis_research.component_registry.contracts import (
        ComponentSelection,
        StrategyManifest,
    )
    from research.aegis_research.component_registry.registry import (
        discover_component_registry,
    )

    example_src = Path(
        "research/aegis_research/component_registry/strategy_example.py"
    )
    dest = tmp_path / "research" / "components" / "strategies" / "example_ma_cross.py"
    dest.parent.mkdir(parents=True)
    shutil.copy(example_src, dest)

    monkeypatch.chdir(tmp_path)
    registry = discover_component_registry(
        root=tmp_path / "research" / "components",
        repo_root=tmp_path,
    )

    assert registry.ids("strategies") == ("example.ma_cross",)
    definition = registry.get(ComponentSelection("strategies", "example.ma_cross"))
    manifest = definition.manifest
    assert isinstance(manifest, StrategyManifest)
    assert manifest.id == "example.ma_cross"
    assert manifest.version == "1.0.0"
    assert manifest.input_names == ("Close",)
    assert manifest.param_names == ("fast_window", "slow_window")
    assert manifest.output_name == "active"
    assert manifest.consumes_outputs == ()
    assert manifest.defaults == {"fast_window": 10, "slow_window": 20}
    assert manifest.owns_portfolio is False
    assert definition.has_param_space is True


def test_show_strategy_schema_guide_embeds_example_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide embeds the complete example source under ## Complete Example."""
    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out
    # The example source is embedded as a code block
    assert "## Complete Example" in markdown
    # Key lines from the example
    assert 'COMPONENT_MANIFEST = {' in markdown
    assert '"family": "strategies"' in markdown
    assert '"id": "example.ma_cross"' in markdown
    assert "def run(inputs, *, n_candidates, **param_lists):" in markdown


def test_show_components_unchanged_after_strategy_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`aerd show components` behavior is unchanged."""
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research/components/indicators/returns.py")
    write_strategy_component(tmp_path / "research/components/strategies/strategy.py")

    assert cli.main(["show", "components", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert "fingerprint" in payload
    assert "families" in payload


def test_show_splitters_catalog_unchanged_after_strategy_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`aerd show splitters` behavior is unchanged."""
    assert cli.main(["show", "splitters", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "splitter_catalog.v1"
    assert any(method["method"] == "from_rolling" for method in payload["methods"])


def test_authoring_story_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: the example Run Config referencing the packaged example
    Indicator and Strategy components validates through the real validation
    coordinator."""
    import shutil

    from research.aegis_research.configuration import (
        CONFIG_SCHEMA_VERSION,
        resolve_run_config,
    )

    # Copy both packaged examples into the component tree
    indicator_src = Path(
        "research/aegis_research/component_registry/indicator_example.py"
    )
    strategy_src = Path(
        "research/aegis_research/component_registry/strategy_example.py"
    )
    indicator_dest = tmp_path / "research" / "components" / "indicators" / "example_ma.py"
    strategy_dest = tmp_path / "research" / "components" / "strategies" / "example_ma_cross.py"
    indicator_dest.parent.mkdir(parents=True)
    strategy_dest.parent.mkdir(parents=True)
    shutil.copy(indicator_src, indicator_dest)
    shutil.copy(strategy_src, strategy_dest)

    monkeypatch.chdir(tmp_path)

    example_raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "authoring.story",
        "data": {
            "source": "synthetic",
            "symbols": ["A", "B", "C"],
            "rows": 250,
            "arrays": ["OHLCV"],
        },
        "portfolio": {
            "gross_cap": 1.0,
            "direction": "longonly",
        },
        "strategy": {"id": "example.ma_cross"},
        "indicators": [{"id": "example.ma"}],
        "ranking": {"metric": "sharpe_ratio"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 126, "split": 0.5},
                "max_splits": 2,
            },
        },
    }

    resolved = resolve_run_config(example_raw)
    assert resolved is not None
    assert resolved.config.name == "authoring.story"
    assert resolved.config.strategy.id == "example.ma_cross"
    assert resolved.config.indicators[0].id == "example.ma"


# ── Drift tests: contract facts asserted against rendered guide output ──────
#
# These tests replace the doc-file string assertions that previously guarded
# contract facts in docs/components.md and research/configs/README.md.
# Contract facts (field requiredness, enum members, entry-point names,
# return shapes) are now asserted against the rendered guide output from
# aerd show config-schema / indicator-schema / strategy-schema.


def _render_guide(subcommand: str) -> str:
    """Render a schema guide and return the markdown output."""
    from research.aegis_research.component_registry.indicator_guide import (
        render_indicator_schema_guide,
    )
    from research.aegis_research.component_registry.strategy_guide import (
        render_strategy_schema_guide,
    )
    from research.aegis_research.configuration.config_schema_guide import (
        render_config_schema_guide,
    )

    renderers = {
        "config-schema": render_config_schema_guide,
        "indicator-schema": render_indicator_schema_guide,
        "strategy-schema": render_strategy_schema_guide,
    }
    return renderers[subcommand]()


# ── config-schema drift assertions ────────────────────────────────────────


def test_config_schema_guide_states_all_portfolio_directions() -> None:
    """Drift: portfolio direction enum members are interpolated from code."""
    guide = _render_guide("config-schema")
    assert "`longonly`" in guide
    assert "`shortonly`" in guide
    assert "`both`" in guide


def test_config_schema_guide_states_all_search_policies() -> None:
    """Drift: optimization search policy enum members are interpolated from code."""
    guide = _render_guide("config-schema")
    assert "`grid`" in guide
    assert "`random`" in guide


def test_config_schema_guide_states_all_lock_roles() -> None:
    """Drift: lock role enum members are interpolated from code."""
    guide = _render_guide("config-schema")
    assert "`best`" in guide
    assert "`median`" in guide
    assert "`worst`" in guide


def test_config_schema_guide_states_all_signal_policies_and_timings() -> None:
    """Drift: signal policy and timing catalogs are interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Signal Policies" in guide
    assert "Signal Execution Timings" in guide


def test_config_schema_guide_states_all_data_array_shortcuts() -> None:
    """Drift: data-array shortcut catalog is interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Data-Array Shortcuts" in guide
    assert "`OHLCV`" in guide


def test_config_schema_guide_states_allowed_degradations() -> None:
    """Drift: allowed data-quality degradations catalog is interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Allowed Data-Quality Degradations" in guide


def test_config_schema_guide_states_missing_policies() -> None:
    """Drift: missing-index/missing-columns policies catalog is interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Missing-Index / Missing-Columns Policies" in guide


def test_config_schema_guide_states_reserved_execute_keys() -> None:
    """Drift: reserved optimization.execute keys are interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Reserved `optimization.execute` Keys" in guide


def test_config_schema_guide_marks_optimization_required() -> None:
    """Drift: the forward contract requires optimization (not optional)."""
    guide = _render_guide("config-schema")
    assert "optimization`** — required" in guide
    assert "forward contract requires" in guide.lower()


def test_config_schema_guide_marks_schema_version_const() -> None:
    """Drift: schema_version is marked as const 8 (not a model default)."""
    guide = _render_guide("config-schema")
    assert "schema_version`** — must be present and exactly `8`" in guide


def test_config_schema_guide_states_allowed_data_sources() -> None:
    """Drift: data source whitelist is interpolated from code."""
    guide = _render_guide("config-schema")
    assert "`synthetic`" in guide
    assert "`csv`" in guide


def test_config_schema_guide_states_removed_fields_unknown() -> None:
    """Drift: labeler/train/model are called out as removed/unknown."""
    guide = _render_guide("config-schema")
    assert "`labeler`" in guide
    assert "`train`" in guide
    assert "`model`" in guide
    assert "rejected as unknown" in guide


def test_config_schema_guide_documents_lock_syntax() -> None:
    """Drift: lock scalar and mapping syntax is documented."""
    guide = _render_guide("config-schema")
    assert "lock: run_id[:role]" in guide
    assert "lock:" in guide
    assert "run_id:" in guide
    assert "candidate_id:" in guide


def test_config_schema_guide_points_at_other_show_commands() -> None:
    """Drift: the guide points at aerd show splitters and aerd show components."""
    guide = _render_guide("config-schema")
    assert "`aerd show splitters <method>`" in guide
    assert "`aerd show components`" in guide


def test_config_schema_guide_sets_not_configurable() -> None:
    """Drift: set_labels is called out as forbidden/not configurable."""
    guide = _render_guide("config-schema")
    assert "set_labels" in guide
    assert "forbidden" in guide.lower() or "not configurable" in guide.lower()


# ── indicator-schema drift assertions ─────────────────────────────────────


def test_indicator_schema_guide_states_all_manifest_fields() -> None:
    """Drift: all manifest fields are in the indicator guide (interpolated)."""
    guide = _render_guide("indicator-schema")
    assert "| `family` |" in guide
    assert "| `id` |" in guide
    assert "| `version` |" in guide
    assert "| `input_names` |" in guide
    assert "| `param_names` |" in guide
    assert "| `defaults` |" in guide
    assert "| `output_names` |" in guide


def test_indicator_schema_guide_states_entry_point_names_from_code() -> None:
    """Drift: entry-point names are interpolated from code constants."""
    from research.aegis_research.component_registry.contracts import (
        COMPONENT_ENTRYPOINT,
        COMPONENT_PARAM_SPACE_ENTRYPOINT,
    )

    guide = _render_guide("indicator-schema")
    assert f"`{COMPONENT_ENTRYPOINT}` Entry Point" in guide
    assert f"`{COMPONENT_PARAM_SPACE_ENTRYPOINT}`" in guide


def test_indicator_schema_guide_documents_batched_signature() -> None:
    """Drift: the batched run signature is documented."""
    guide = _render_guide("indicator-schema")
    assert "n_candidates" in guide
    assert "param_lists" in guide


def test_indicator_schema_guide_documents_mapping_return() -> None:
    """Drift: the mapping-of-outputs return contract is documented."""
    guide = _render_guide("indicator-schema")
    assert "mapping" in guide.lower()
    assert "output name to candidate-major" in guide


def test_indicator_schema_guide_documents_candidate_major_layout() -> None:
    """Drift: the candidate-major block layout is documented."""
    guide = _render_guide("indicator-schema")
    assert "candidate_index * n_symbols" in guide
    assert "n_candidates * n_symbols" in guide


def test_indicator_schema_guide_documents_batch_invariance() -> None:
    """Drift: the batch-invariance rule is documented."""
    guide = _render_guide("indicator-schema")
    assert "Batch-Invariance" in guide
    assert "bitwise" in guide


def test_indicator_schema_guide_documents_legacy_declarations_as_errors() -> None:
    """Drift: legacy callable keys are documented as hard errors."""
    guide = _render_guide("indicator-schema")
    assert "COMPONENT_CALLABLE" in guide
    assert "wide_callable" in guide
    assert "param_space_callable" in guide
    assert "hard error" in guide.lower()


def test_indicator_schema_guide_embeds_packaged_example() -> None:
    """Drift: the packaged example component is embedded in the guide."""
    guide = _render_guide("indicator-schema")
    assert "## Complete Example" in guide
    assert '"id": "example.ma"' in guide
    assert "def run(data, *, n_candidates, **param_lists):" in guide


# ── strategy-schema drift assertions ──────────────────────────────────────


def test_strategy_schema_guide_states_all_manifest_fields() -> None:
    """Drift: all manifest fields are in the strategy guide."""
    guide = _render_guide("strategy-schema")
    assert "| `family` |" in guide
    assert "| `id` |" in guide
    assert "| `version` |" in guide
    assert "| `input_names` |" in guide
    assert "| `param_names` |" in guide
    assert "| `defaults` |" in guide
    assert "| `output_name` |" in guide
    assert "| `consumes_outputs` |" in guide
    assert "| `owns_portfolio` |" in guide


def test_strategy_schema_guide_states_allocation_outputs_from_code() -> None:
    """Drift: all registered allocation outputs are interpolated from code."""
    from research.aegis_research.component_registry.contracts import (
        STRATEGY_ALLOCATION_OUTPUTS,
    )

    guide = _render_guide("strategy-schema")
    for output_name in sorted(STRATEGY_ALLOCATION_OUTPUTS):
        assert f"`{output_name}`" in guide


def test_strategy_schema_guide_documents_inputs_object() -> None:
    """Drift: the inputs object attributes are documented."""
    guide = _render_guide("strategy-schema")
    assert "`inputs.data`" in guide
    assert "`inputs.indicators`" in guide
    assert "`inputs.n_symbols`" in guide
    assert "`inputs.metadata`" in guide


def test_strategy_schema_guide_documents_bare_array_return() -> None:
    """Drift: the bare allocation-array return is documented (not a mapping)."""
    guide = _render_guide("strategy-schema")
    assert "bare" in guide.lower()
    assert "not a mapping" in guide.lower()


def test_strategy_schema_guide_documents_nan_selection() -> None:
    """Drift: the NaN-selection convention is documented."""
    guide = _render_guide("strategy-schema")
    assert "NaN-Selection Convention" in guide
    assert "NaN = excluded" in guide


def test_strategy_schema_guide_documents_ownership_boundaries() -> None:
    """Drift: component vs config/policy ownership boundaries are documented."""
    guide = _render_guide("strategy-schema")
    assert "portfolio.gross_cap" in guide
    assert "portfolio.direction" in guide
    assert "owns_portfolio" in guide


def test_strategy_schema_guide_documents_consumes_outputs_wiring() -> None:
    """Drift: consumes_outputs wiring contract is documented."""
    guide = _render_guide("strategy-schema")
    assert "consumes_outputs" in guide
    assert "wiring contract" in guide.lower()


def test_strategy_schema_guide_states_entry_point_names_from_code() -> None:
    """Drift: entry-point names are interpolated from code constants."""
    from research.aegis_research.component_registry.contracts import (
        COMPONENT_ENTRYPOINT,
        COMPONENT_PARAM_SPACE_ENTRYPOINT,
    )

    guide = _render_guide("strategy-schema")
    assert f"`{COMPONENT_ENTRYPOINT}` Entry Point" in guide
    assert f"`{COMPONENT_PARAM_SPACE_ENTRYPOINT}`" in guide


def test_strategy_schema_guide_embeds_packaged_example() -> None:
    """Drift: the packaged strategy example is embedded in the guide."""
    guide = _render_guide("strategy-schema")
    assert "## Complete Example" in guide
    assert '"id": "example.ma_cross"' in guide
    assert "def run(inputs, *, n_candidates, **param_lists):" in guide
