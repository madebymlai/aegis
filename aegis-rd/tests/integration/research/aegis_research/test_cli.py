from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.cli_commands import run as run_command
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
    seed_catalog_ohlcv,
)


def test_root_help_identifies_aerd(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0

    output = capsys.readouterr()
    assert "usage: aerd" in output.out
    assert "run" in output.out
    assert "export" in output.out
    assert "show" in output.out
    assert "train" not in output.out
    assert "play" not in output.out


def test_run_help_does_not_list_train_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "--help"]) == 0

    output = capsys.readouterr()
    assert "--train" not in output.out
    assert "Run the config's train section" not in output.out


def test_show_components_lists_registry_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research/components/indicators/returns.py")
    write_strategy_component(tmp_path / "research/components/strategies/strategy.py")

    assert cli.main(["show", "components"]) == 0

    payload = json.loads(capsys.readouterr().out)
    strategy = payload["families"]["strategies"]["demo.strategy"]
    indicator = payload["families"]["indicators"]["demo.returns"]
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert payload["fingerprint"]
    assert strategy["output_name"] == "active"
    assert strategy["params"]["param_space"]["available"] is False
    assert indicator["outputs"] == ["returns"]


def test_preparse_error_is_json_without_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Pre-parse failures emit JSON error envelope without --json flag."""
    assert cli.main(["nope"]) == 2

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["status"] == "error"
    assert payload["error"]["category"] == "invocation"


def test_interrupted_error_is_json_without_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """KeyboardInterrupt emits JSON error envelope without --json flag."""

    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_parser", interrupt)

    assert cli.main([]) == 130

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "interrupted"


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
    assert cli.main(["run"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "requires an explicit config" in payload["error"]["message"]
    assert "--train" not in payload["error"]["message"]


def test_run_rejects_removed_json_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """aerd run --json exits with an unrecognized-argument error."""
    assert cli.main(["run", "config.yaml", "--json"]) == 2

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "invocation"
    assert "--json" in payload["error"]["message"]


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--train", "config.yaml"],
        ["run", "config.yaml", "--train"],
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


def test_run_success_payload_is_the_emitted_json_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    write_strategy_component(tmp_path / "research/components/strategies/strategy.py")
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "stubbed_run",
                "output_dir": "runs",
                "data": native_data_config_payload(instruments=["SYN.XNAS"]),
                "portfolio": {"direction": "longonly"},
                "strategy": {"id": "demo.strategy"},
                "indicators": [],
                "ranking": {"metric": "total_return"},
                "optimization": {
                    "search": "grid",
                    "observation_block_bars": 20,
                },
            },
            sort_keys=False,
        )
    )
    long_base = tmp_path.joinpath(*(f"long-path-segment-{i:02d}" for i in range(35)))
    artifact_path = long_base / "strategy_run.json"
    store_path = long_base / ".candidate_store" / "candidates.sqlite3"

    def stub_run_strategy_sweep(*_args: object, **kwargs: object) -> dict[str, object]:
        return {
            "run_id": kwargs["run_id"],
            "status": "completed",
            "run_dir": str(long_base),
            "manifest_path": str(long_base / "manifest.json"),
            "started_at": "2026-06-12T00:00:00Z",
            "finished_at": "2026-06-12T00:01:00Z",
            "strategy_artifact_id": "strategy.run",
            "strategy_artifact_path": str(artifact_path),
            "candidate_store_path": str(store_path),
            "optimization": {"total": 4, "protocol": "continuous_future_in_past"},
            "candidates": [{"role": "best", "lock": kwargs["run_id"]}],
        }

    monkeypatch.setattr(run_command, "run_strategy_sweep", stub_run_strategy_sweep)

    assert cli.main(["run", str(config_path), "--run-id", "stubbed-success"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["command"] == "run"
    assert payload["selection"] == {
        "source": "explicit",
        "config_path": str(config_path.resolve()),
    }
    assert payload["run"] == {
        "id": "stubbed-success",
        "status": "completed",
        "run_dir": str(long_base.resolve(strict=False)),
        "manifest_path": str((long_base / "manifest.json").resolve(strict=False)),
        "started_at": "2026-06-12T00:00:00Z",
        "finished_at": "2026-06-12T00:01:00Z",
    }
    assert payload["artifacts"] == {
        "strategy_artifact_id": "strategy.run",
        "strategy_artifact_path": str(artifact_path.resolve(strict=False)),
    }
    assert payload["candidate_store"] == {
        "path": str(store_path.resolve(strict=False)),
    }
    assert payload["optimization"] == {
        "total": 4,
        "protocol": "continuous_future_in_past",
    }
    assert payload["candidates"] == [{"role": "best", "lock": "stubbed-success"}]


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
                "data": native_data_config_payload(instruments=["SYN.XNAS"]),
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"id": "missing_strategy"},
                "labeler": {"id": "demo.fixlb"},
                "indicators": [{"id": "missing_indicator"}],
                "ranking": {"metric": "total_return", "direction": "desc"},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--run-id", "bad-run"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "labeler: Unexpected keyword argument" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-run").exists()


def _signed_book_run_config(
    direction: str,
    *,
    catalog_path: Path | None = None,
) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "directional_run",
        "output_dir": "runs",
        "data": native_data_config_payload(
            instruments=["SYN.XNAS"],
            end="2024-04-30",
            path=catalog_path,
        ),
        "portfolio": {"direction": direction},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "observation_block_bars": 20,
        },
    }


def test_run_rejects_unknown_portfolio_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "run.yaml"
    config_path.write_text(yaml.safe_dump(_signed_book_run_config("sideways"), sort_keys=False))

    assert cli.main(["run", str(config_path), "--run-id", "bad-dir"]) == 6

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
    seed_catalog_ohlcv(tmp_path / "catalog", ["SYN.XNAS"], periods=120)
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            _signed_book_run_config("shortonly", catalog_path=tmp_path / "catalog"),
            sort_keys=False,
        )
    )

    cli.main(["run", str(config_path), "--run-id", "short-dir"])

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "portfolio.direction" not in combined


def _carry_run_config(
    short_borrow_rate: float | None,
    *,
    catalog_path: Path,
) -> dict[str, object]:
    config = _signed_book_run_config("both", catalog_path=catalog_path)
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
        yaml.safe_dump(
            _carry_run_config(
                short_borrow_rate,
                catalog_path=tmp_path / "catalog",
            ),
            sort_keys=False,
        )
    )
    assert cli.main(["run", str(config_path), "--run-id", run_id]) == 0
    artifact = json.loads((tmp_path / "runs" / run_id / "strategy_run.json").read_text())
    return [
        candidate["complete_period_metrics"]["total_return"] for candidate in artifact["candidates"]
    ]


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
    seed_catalog_ohlcv(tmp_path / "catalog", ["SYN.XNAS"], periods=120)

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
                "data": native_data_config_payload(instruments=["SYN.XNAS"]),
                "portfolio": {"entry_budget": 1.0},
                "labeler": {"id": "demo.fixlb"},
                "indicators": [{"id": "demo.returns"}],
                "train": {"model": {"source": "plugin", "id": "demo.model"}},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--run-id", "bad-mode"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert "Unexpected keyword argument" in payload["error"]["message"]
    assert "aerd run --train" not in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-mode").exists()


def test_top_level_keyboard_interrupt_is_structured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_parser", interrupt)

    assert cli.main([]) == 130

    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "interrupted"


def test_output_helper_normalizes_nonstandard_json_numbers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from research.aegis_research.cli_support.output import CommandResult, write_success

    assert write_success(CommandResult(command="test", payload={"value": float("nan")})) == 0

    assert json.loads(capsys.readouterr().out)["value"] is None


def test_error_details_paths_emit_real_resolved_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The JSON sanitizer's Path branch emits real absolute paths — the
    scrubbing rewrite (ADR-0009's retired threat model) is gone (ADR-0021)."""
    from research.aegis_research.cli_support.output import jsonable_value

    monkeypatch.chdir(tmp_path)

    assert jsonable_value(Path("runs/example")) == str(tmp_path / "runs" / "example")
    assert jsonable_value(Path("/data/runs/abc")) == "/data/runs/abc"


def test_run_refs_emits_absolute_paths_unscrubbed() -> None:
    """The run-refs projection emits real absolute paths — no scrubbing."""
    from research.aegis_research.cli_support.output import run_refs

    refs: dict[str, object] = {
        "run_id": "abc123",
        "status": "success",
        "run_dir": "/data/runs/abc123",
        "manifest_path": "/data/runs/abc123/manifest.json",
        "started_at": "2026-06-12T00:00:00Z",
        "finished_at": "2026-06-12T00:01:00Z",
    }
    block = run_refs(refs)
    assert block["id"] == "abc123"
    assert block["run_dir"] == "/data/runs/abc123"
    assert block["manifest_path"] == "/data/runs/abc123/manifest.json"


def test_run_refs_resolves_relative_paths_against_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relative pipeline paths resolve to real absolute paths (ADR-0021)."""
    from research.aegis_research.cli_support.output import run_refs

    monkeypatch.chdir(tmp_path)
    block = run_refs({"run_id": "x", "run_dir": "runs/x", "manifest_path": "runs/x/manifest.json"})
    assert block["run_dir"] == str(tmp_path / "runs" / "x")
    assert block["manifest_path"] == str(tmp_path / "runs" / "x" / "manifest.json")


def test_run_refs_stringifies_path_values() -> None:
    """Path-typed refs become strings in the projection, so the success
    envelope's JSON sanitizer (whose Path branch scrubs) never sees a Path."""
    from pathlib import Path

    from research.aegis_research.cli_support.output import run_refs

    block = run_refs(
        {
            "run_id": "abc123",
            "run_dir": Path("/data/runs/abc123"),
            "manifest_path": Path("/data/runs/abc123/manifest.json"),
        }
    )
    assert block["run_dir"] == "/data/runs/abc123"
    assert block["manifest_path"] == "/data/runs/abc123/manifest.json"


# ── config-schema show subcommand ────────────────────────────────────────────


def test_show_config_schema_exits_zero_and_prints_markdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human mode prints markdown with key contract sections."""
    assert cli.main(["show", "config-schema"]) == 0

    output = capsys.readouterr()
    guide = output.out

    assert "# Run Config Forward Contract" in guide
    assert "## Structural Contract" in guide
    assert "## Top-Level Fields" in guide
    assert "## Literal Catalogs" in guide
    assert "observation_block_bars" in guide
    assert "## Component IDs" in guide
    assert "## Example Run Config" in guide

    assert "| `optimization` | `OptimizationConfig` | yes | — | — |" in guide
    assert "| `schema_version` | `11` | yes | — | exactly `11` |" in guide

    # Pointers to other show subcommands
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
    assert payload["schema_version"] == "config_schema_guide.v1"

    content = payload["content"]
    assert isinstance(content, str)
    assert len(content) > 1000  # Full guide, not clipped
    assert "# Run Config Forward Contract" in content
    assert "## Structural Contract" in content
    assert "## Literal Catalogs" in content


def test_show_config_schema_marks_model_required_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The rendered guide states requiredness from the validating model."""
    assert cli.main(["show", "config-schema"]) == 0

    guide = capsys.readouterr().out

    assert "| `optimization` | `OptimizationConfig` | yes | — | — |" in guide
    assert "| `schema_version` | `11` | yes | — | exactly `11` |" in guide


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


def test_show_config_schema_points_at_components_and_internal_block_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide points at Components while keeping Splitter policy internal."""
    assert cli.main(["show", "config-schema"]) == 0

    guide = capsys.readouterr().out

    assert "`aerd show components`" in guide
    assert "Splitter construction and application are internal policy" in guide


def test_show_config_schema_documents_native_data_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide documents native ids, not legacy source/provider selectors."""
    assert cli.main(["show", "config-schema"]) == 0
    guide = capsys.readouterr().out

    assert "`instruments`" in guide
    assert "`exchange`" in guide
    assert "native Nautilus `InstrumentId`" in guide
    assert "data.source" in guide
    assert "Continuous-Futures Adjustment Modes" not in guide
    assert "pnl_adjustment" not in guide


def test_show_config_schema_embeds_continuous_future_example(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide carries a worked continuous-future example snippet."""
    assert cli.main(["show", "config-schema"]) == 0
    guide = capsys.readouterr().out

    assert "## Example: Continuous Future" in guide
    assert "ESZ6.XCME" in guide
    assert "futures: [ES]" in guide
    assert "source: store" not in guide


def test_show_config_schema_continuous_future_example_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The embedded continuous-future YAML validates through the real validation coordinator."""
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research" / "components" / "indicators" / "returns.py")
    write_strategy_component(tmp_path / "research" / "components" / "strategies" / "strategy.py")

    assert cli.main(["show", "config-schema"]) == 0
    guide = capsys.readouterr().out

    raw = yaml.safe_load(_yaml_block_after(guide, "## Example: Continuous Future"))

    from research.aegis_research.configuration import resolve_run_config

    resolved = resolve_run_config(raw)
    assert resolved.config.data.instruments == ["ESZ6.XCME"]
    assert resolved.config.data.futures == ["ES"]
    assert resolved.config.data.exchange == []
    assert not hasattr(resolved.config.data, "source")


def _yaml_block_after(guide: str, heading: str) -> str:
    """Return the first fenced ```yaml block following ``heading`` in the guide."""
    start = guide.index(heading)
    fence = guide.index("```yaml", start) + len("```yaml")
    end = guide.index("```", fence)
    return guide[fence:end]


def test_show_config_schema_embedded_example_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The embedded example Run Config YAML validates through the real
    validation coordinator with wired demo components."""
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research" / "components" / "indicators" / "returns.py")
    write_strategy_component(tmp_path / "research" / "components" / "strategies" / "strategy.py")

    from research.aegis_research.configuration import (
        CONFIG_SCHEMA_VERSION,
        resolve_run_config,
    )

    example_raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "example.run",
        "data": {
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ", "MSFT.NASDAQ", "SPY.ARCA"],
            "exchange": ["EUR/USD.IDEALPRO"],
            "arrays": ["OHLCV"],
            "start": "2024-01-01",
            "end": "2024-12-31",
            "timeframe": "1D",
        },
        "portfolio": {
            "direction": "longonly",
        },
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "sharpe_ratio"},
        "optimization": {
            "search": "grid",
            "observation_block_bars": 63,
        },
    }

    resolved = resolve_run_config(example_raw)
    assert resolved is not None
    assert resolved.config.name == "example.run"
    assert resolved.config.data.instruments == ["AAPL.NASDAQ", "MSFT.NASDAQ", "SPY.ARCA"]
    assert resolved.config.portfolio.direction == "longonly"
    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "grid"


def test_show_config_schema_coherence_optimization_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide and validation both expose model-owned requiredness."""
    from research.aegis_research.configuration import (
        CONFIG_SCHEMA_VERSION,
        ConfigValidationError,
        resolve_run_config,
    )

    # Side A: guide states optimization required
    assert cli.main(["show", "config-schema"]) == 0
    guide = capsys.readouterr().out
    assert "| `optimization` | `OptimizationConfig` | yes | — | — |" in guide

    # Side B: config omitting optimization fails validation
    monkeypatch.chdir(tmp_path)
    write_indicator_component(tmp_path / "research" / "components" / "indicators" / "returns.py")
    write_strategy_component(tmp_path / "research" / "components" / "strategies" / "strategy.py")

    raw_no_optimization = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "test",
        "data": native_data_config_payload(instruments=["A.XNAS"], end="2024-04-10"),
        "portfolio": {"direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "sharpe_ratio"},
    }

    with pytest.raises(ConfigValidationError) as exc_info:
        resolve_run_config(raw_no_optimization)

    issues = {i.path: i.message for i in exc_info.value.issues}
    assert issues["optimization"] == "Field required"


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
    assert "## Complete Example" in markdown

    # v2 contract = run entry point
    assert "`run`" in markdown
    # Batched signature
    assert "n_candidates" in markdown
    # Mapping return contract
    assert 'return {"ma": result}' in markdown or 'return {"ma":' in markdown
    # Candidate-major layout
    assert "candidate_index * n_symbols" in markdown
    # Pink-elephant rule: the guide never names the rejected legacy keys
    assert "## Legacy Declarations" not in markdown
    assert "COMPONENT_CALLABLE" not in markdown
    assert "wide_callable" not in markdown
    assert "param_space_callable" not in markdown


def test_show_indicator_schema_json_returns_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "indicator-schema", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["format"] == "markdown"
    assert payload["schema_version"] == "indicator_schema_guide.v1"

    content = payload["content"]
    assert "# Indicator Component Authoring Guide" in content
    assert len(content) > 1000  # Full guide, not clipped to MAX_REASON_CHARS
    # A marker from the embedded example at the very end of the guide: proves
    # the whole document survives JSON serialization, not just the title.
    assert '"id": "example.ma"' in content


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

    from research.aegis_research.component_registry.contracts import ComponentSelection
    from research.aegis_research.component_registry.registry import (
        discover_component_registry,
    )

    example_src = Path("research/aegis_research/component_registry/indicator_example.py")
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
    assert definition.id == "example.ma"
    assert definition.version == "1.0.0"
    assert definition.input_names == ("Close",)
    assert definition.declared_param_names() == ("window", "wtype")
    assert definition.produced_output_names() == ("ma",)
    assert definition.default_params() == {"window": 20, "wtype": "simple"}
    assert definition.load_param_space() is not None


def test_show_indicator_schema_guide_embeds_example_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide embeds the complete example source under ## Complete Example."""
    assert cli.main(["show", "indicator-schema"]) == 0

    markdown = capsys.readouterr().out
    # The example source is embedded as a code block
    assert "## Complete Example" in markdown
    # Key lines from the example
    assert "COMPONENT_MANIFEST = {" in markdown
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

    assert cli.main(["show", "components"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert "fingerprint" in payload
    assert "families" in payload


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
    assert "## Complete Example" in markdown

    # v2 contract = run entry point
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
    assert "SLEEVE_GROSS_LIMIT" in markdown
    assert "owns_portfolio" in markdown
    # NaN-selection convention
    assert "NaN" in markdown
    assert "np.nan" in markdown
    # Pink-elephant rule: the guide never names the rejected legacy keys
    assert "## Legacy Declarations" not in markdown
    assert "COMPONENT_CALLABLE" not in markdown
    assert "wide_callable" not in markdown
    assert "param_space_callable" not in markdown


def test_show_strategy_schema_json_returns_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["show", "strategy-schema", "--json"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["format"] == "markdown"
    assert payload["schema_version"] == "strategy_schema_guide.v1"

    content = payload["content"]
    assert "# Strategy Component Authoring Guide" in content
    assert len(content) > 1000  # Full guide, not clipped to MAX_REASON_CHARS
    # A heading near the end of the guide: proves the whole document survives
    # JSON serialization, not just the title in the first MAX_REASON_CHARS.
    assert "## Complete Example" in content


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

    from research.aegis_research.component_registry.contracts import ComponentSelection
    from research.aegis_research.component_registry.registry import (
        discover_component_registry,
    )

    example_src = Path("research/aegis_research/component_registry/strategy_example.py")
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
    assert definition.id == "example.ma_cross"
    assert definition.version == "1.0.0"
    assert definition.input_names == ("Close",)
    assert definition.declared_param_names() == ("fast_window", "slow_window")
    assert definition.allocation_output_name() == "active"
    assert definition.consumed_output_names() == ()
    assert definition.default_params() == {"fast_window": 10, "slow_window": 20}
    assert definition.public_snapshot()["owns_portfolio"] is False
    assert definition.load_param_space() is not None


def test_show_strategy_schema_guide_embeds_example_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The guide embeds the complete example source under ## Complete Example."""
    assert cli.main(["show", "strategy-schema"]) == 0

    markdown = capsys.readouterr().out
    # The example source is embedded as a code block
    assert "## Complete Example" in markdown
    # Key lines from the example
    assert "COMPONENT_MANIFEST = {" in markdown
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

    assert cli.main(["show", "components"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["schema_version"] == "component_registry_snapshot.v1"
    assert "fingerprint" in payload
    assert "families" in payload


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
    indicator_src = Path("research/aegis_research/component_registry/indicator_example.py")
    strategy_src = Path("research/aegis_research/component_registry/strategy_example.py")
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
        "data": native_data_config_payload(
            instruments=["A.XNAS", "B.XNAS", "C.XNAS"],
            end="2024-09-07",
        ),
        "portfolio": {
            "direction": "longonly",
        },
        "strategy": {"id": "example.ma_cross"},
        "indicators": [{"id": "example.ma"}],
        "ranking": {"metric": "sharpe_ratio"},
        "optimization": {
            "search": "grid",
            "observation_block_bars": 63,
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
    assert "Allowed Data-Quality Degradations" not in guide


def test_config_schema_guide_states_missing_policies() -> None:
    """Drift: the missing-index policy catalog is interpolated from code."""
    guide = _render_guide("config-schema")
    assert "Missing-Index Policy" in guide


def test_config_schema_guide_marks_optimization_required() -> None:
    """Drift: the validating model requires optimization."""
    guide = _render_guide("config-schema")
    assert "| `optimization` | `OptimizationConfig` | yes | — | — |" in guide


def test_config_schema_guide_marks_schema_version_required_and_exact() -> None:
    """Drift: the validating model requires schema version 11."""
    guide = _render_guide("config-schema")
    assert "| `schema_version` | `11` | yes | — | exactly `11` |" in guide


def test_config_schema_guide_derives_run_name_constraints() -> None:
    guide = _render_guide("config-schema")
    assert (
        "| `name` | `str` | yes | — | "
        "must match `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]*|\\."
        "[A-Za-z0-9_-][A-Za-z0-9_.-]*|\\.\\.[A-Za-z0-9_.-]+)$` |"
        in guide
    )


def test_config_schema_guide_states_native_data_contract() -> None:
    """Drift: data contract documents native ids, not source selectors."""
    guide = _render_guide("config-schema")
    assert "`instruments`" in guide
    assert "`exchange`" in guide
    assert "native Nautilus `InstrumentId`" in guide
    assert "`synthetic`" not in guide
    assert "`csv`" not in guide


def test_config_schema_guide_documents_band_override_shape() -> None:
    """Drift: per-instrument bands document native-id and futures-root keys."""
    guide = _render_guide("config-schema")
    assert "`band_overrides`" in guide
    assert "native `data.instruments` ids" in guide
    assert "bare `data.futures` roots" in guide
    assert "AAPL.NASDAQ:" in guide
    assert "ES:" in guide
    assert "up: 0.03" in guide
    assert "down: 0.08" in guide


def test_config_schema_guide_states_removed_fields_unknown() -> None:
    """Drift: labeler/train/model are called out as removed/unknown."""
    guide = _render_guide("config-schema")
    assert "`data.source`" in guide
    assert "`data.symbols`" in guide
    assert "`data.provider`" in guide
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


def test_config_schema_guide_points_at_component_command_only() -> None:
    """Drift: public config does not expose the internal Splitter catalog."""
    guide = _render_guide("config-schema")
    assert "`aerd show components`" in guide
    assert "`aerd show splitters <method>`" not in guide


def test_config_schema_guide_contains_no_splitter_kwargs() -> None:
    """Drift: VBT Splitter kwargs never appear as Run Config choices."""
    guide = _render_guide("config-schema")
    assert "set_labels" not in guide
    assert "observation_block_bars" in guide


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


def test_indicator_schema_guide_omits_legacy_declarations() -> None:
    """Pink-elephant rule: naming the rejected legacy keys would teach the very
    patterns the v2 contract forbids, so the guide must never mention them."""
    guide = _render_guide("indicator-schema")
    assert "## Legacy Declarations" not in guide
    assert "COMPONENT_CALLABLE" not in guide
    assert "wide_callable" not in guide
    assert "param_space_callable" not in guide


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
    assert "SLEEVE_GROSS_LIMIT" in guide
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


def test_strategy_schema_guide_omits_legacy_declarations() -> None:
    """Pink-elephant rule: naming the rejected legacy keys would teach the very
    patterns the v2 contract forbids, so the guide must never mention them."""
    guide = _render_guide("strategy-schema")
    assert "## Legacy Declarations" not in guide
    assert "COMPONENT_CALLABLE" not in guide
    assert "wide_callable" not in guide
    assert "param_space_callable" not in guide
