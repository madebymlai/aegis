from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli, strategy_runs
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import component_param_key
from research.aegis_research.provenance.manifest import RunStatus


def test_run_cli_rejects_playbook_source_selectors_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            _run_config_payload(
                strategy={"source": "playbook", "id": "ma_cross"},
                indicators=[{"source": "playbook", "ids": ["ma_explore"]}],
            ),
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "removed-playbook"]) == 6

    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["category"] == "config_validation"
    assert "strategy.source" in payload["error"]["message"]
    assert "source selectors are removed" in payload["error"]["message"]
    assert "indicators[0].ids" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "removed-playbook").exists()


def test_run_cli_rejects_candidate_grid_on_component_config_before_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(
        tmp_path,
        candidate_grid={"batch_size": 2},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "candidate-grid"]) == 6

    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["category"] == "config_validation"
    assert "candidate_grid" in payload["error"]["message"]
    assert "removed from the forward run contract" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "candidate-grid").exists()


def test_component_optimization_routes_away_from_custom_candidate_grid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("legacy candidate sweep path should not run for component optimization")

    monkeypatch.setattr(strategy_runs, "compose_candidate_grid", fail_if_called)
    monkeypatch.setattr(strategy_runs, "materialize_strategy_sweep_signals", fail_if_called)
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-boundary"]) == 0

    payload = json.loads(capsys.readouterr().out)
    artifact = json.loads((tmp_path / "runs" / "component-boundary" / "strategy_run.json").read_text())
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"
    fast_key = component_param_key("strategies", "demo.ma_opt", "strategy", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_opt", "strategy", "slow_window")

    assert payload["status"] == "success"
    assert artifact["evidence_type"] == "optimization"
    assert artifact["strategy"]["family"] == "strategies"
    assert artifact["strategy"]["id"] == "demo.ma_opt"
    assert artifact["leaderboard"]["rows"]
    assert artifact["execution"]["sampled_rows"]["index_names"] == [fast_key, slow_key]
    assert len(artifact["execution"]["sampled_rows"]["rows"]) == 4
    assert artifact["candidates"]
    assert set(artifact["candidates"][0]["params"]) == {fast_key, slow_key}
    assert artifact["candidate_store"]["path"] == ".candidate_store/candidates.sqlite3"
    assert store_path.exists()
    with CandidateStore(store_path) as store:
        top = store.top_candidates_by_run("component-boundary", limit=1)
    assert top[0]["leaderboard_row"]["candidate_key"] == artifact["leaderboard"]["rows"][0]["candidate_key"]


def test_component_optimization_runtime_error_records_failure_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_runtime_error_strategy_component(tmp_path / "research/components/strategies/ma_boom.py")
    config_path = _write_run_config(tmp_path, strategy_id="demo.ma_boom")

    exit_code = cli.main(["run", str(config_path), "--json", "--run-id", "runtime-failure"])
    assert exit_code != 0

    manifest = json.loads((tmp_path / "runs" / "runtime-failure" / "manifest.json").read_text())
    payload = json.loads(capsys.readouterr().err)

    assert payload["error"]["category"] == "execution_failure"
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["evidence"]["optimization"]["execution_failure"]["error_type"] == "RuntimeError"
    assert "component optimization failed intentionally" in manifest["stages"][-1]["diagnostic"]["message"]


def test_component_optimization_preflight_failure_records_manifest_without_pipeline_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(
        tmp_path / "research/components/strategies/ma_opt.py",
        windows=range(1_000),
        slow_windows=range(1_000, 2_000),
        fail_if_executed=True,
    )
    split = _rolling_split_config()
    split["max_estimated_output_cells"] = 100
    config_path = _write_run_config(tmp_path, optimization={"search": "grid", "split": split})

    assert cli.main(["run", str(config_path), "--json", "--run-id", "preflight-failure"]) == 10

    manifest = json.loads((tmp_path / "runs" / "preflight-failure" / "manifest.json").read_text())
    payload = json.loads(capsys.readouterr().err)

    assert payload["error"]["category"] == "execution_failure"
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert manifest["evidence"]["optimization"]["preflight_failure"]["error_type"] == "PreflightError"
    assert "exceed optimization.split.max_estimated_output_cells" in manifest["stages"][-1]["diagnostic"]["message"]


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_id: str = "demo.ma_opt",
    candidate_grid: dict[str, object] | None = None,
    optimization: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            _run_config_payload(
                strategy={"id": strategy_id},
                indicators=[],
                candidate_grid=candidate_grid,
                optimization=optimization or {"search": "grid", "split": _rolling_split_config()},
            ),
            sort_keys=False,
        )
    )
    return path


def _run_config_payload(
    *,
    strategy: dict[str, object],
    indicators: list[dict[str, object]],
    candidate_grid: dict[str, object] | None = None,
    optimization: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "component_optimization_contract",
        "output_dir": "runs",
        "data": {
            "source": "synthetic",
            "symbols": ["SYN"],
            "rows": 80,
            "arrays": ["OHLCV"],
        },
        "portfolio": {"entry_budget": 1.0},
        "strategy": strategy,
        "indicators": indicators,
        "ranking": {"metric": "total_return", "direction": "desc"},
        **({"candidate_grid": candidate_grid} if candidate_grid is not None else {}),
        **({"optimization": optimization} if optimization is not None else {}),
    }


def _rolling_split_config() -> dict[str, object]:
    return {
        "method": "from_rolling",
        "params": {
            "length": 20,
            "offset": 20,
            "split": 0.5,
        },
        "max_splits": 5,
    }


def _write_parameterized_strategy_component(
    path: Path,
    *,
    windows: range | list[int] | None = None,
    slow_windows: range | list[int] | None = None,
    fail_if_executed: bool = False,
) -> None:
    fast_values = list(range(2, 4) if windows is None else windows)
    slow_values = list(range(5, 7) if slow_windows is None else slow_windows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized moving-average strategy fixture.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.ma_opt', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['fast_window', 'slow_window'], "
        "'signal_outputs': ['entries', 'exits'], "
        "'defaults': {'fast_window': 2, 'slow_window': 5}, "
        "'param_space_callable': 'param_space', 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% parameter space\n"
        "def param_space():\n"
        f"    return {{'fast_window': vbt.Param({fast_values!r}), "
        f"'slow_window': vbt.Param({slow_values!r})}}\n"
        "\n# %% main compute\n"
        "def run(inputs, fast_window, slow_window):\n"
        '    """Generate moving-average crossover signals."""\n'
        + (
            "    raise RuntimeError('component should not execute after preflight failure')\n"
            if fail_if_executed
            else ""
        )
        + "    close = inputs.data.feature('Close')\n"
        "    fast = close.rolling(int(fast_window), min_periods=1).mean()\n"
        "    slow = close.rolling(int(slow_window), min_periods=1).mean()\n"
        "    return {'entries': fast.gt(slow), 'exits': fast.lt(slow)}\n"
    )


def _write_runtime_error_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture that fails during component optimization execution.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.ma_boom', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'signal_outputs': ['entries', 'exits'], "
        "'defaults': {'window': 2}, 'param_space_callable': 'param_space'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2])}\n"
        "\n# %% main compute\n"
        "def run(inputs, window):\n"
        '    """Raise a deterministic execution failure."""\n'
        "    raise RuntimeError('component optimization failed intentionally')\n"
    )
