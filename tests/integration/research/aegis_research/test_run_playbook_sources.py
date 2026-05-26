from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli, strategy_runs
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.optimization.candidate_store import CandidateStore, CandidateStoreError
from research.aegis_research.optimization.component_source import (
    FIXED_CANDIDATE_PARAM,
    component_param_key,
)
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

    payload = _last_json_line(capsys.readouterr().err)
    assert payload["error"]["category"] == "config_validation"
    assert "strategy.source" in payload["error"]["message"]
    assert "unknown field" in payload["error"]["message"]
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

    payload = _last_json_line(capsys.readouterr().err)
    assert payload["error"]["category"] == "config_validation"
    assert "candidate_grid" in payload["error"]["message"]
    assert "unknown field" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "candidate-grid").exists()


def test_component_optimization_uses_component_native_candidate_grid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-boundary"]) == 0

    payload = json.loads(capsys.readouterr().out)
    artifact = json.loads(
        (tmp_path / "runs" / "component-boundary" / "strategy_run.json").read_text()
    )
    manifest = json.loads((tmp_path / "runs" / "component-boundary" / "manifest.json").read_text())
    artifact_record = next(
        record for record in manifest["artifacts"] if record["id"] == "strategy.run"
    )
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"
    fast_key = component_param_key("strategies", "demo.ma_opt", "strategy", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_opt", "strategy", "slow_window")

    assert payload["status"] == "success"
    assert (
        payload["artifacts"]["strategy_artifact_path"]
        == "runs/component-boundary/strategy_run.json"
    )
    assert payload["candidate_store"]["path"] == "runs/.candidate_store/candidates.sqlite3"
    assert artifact["schema_version"] == "optimization_artifact.v1"
    assert artifact_record["role"] == "optimization_evidence"
    assert artifact_record["schema_version"] == "optimization_artifact.v1"
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
    assert (
        top[0]["leaderboard_row"]["candidate_key"]
        == artifact["leaderboard"]["rows"][0]["candidate_key"]
    )
    assert artifact["locks"][0]["component_family"] == "strategies"
    assert artifact["locks"][0]["component_id"] == "demo.ma_opt"
    assert artifact["locks"][0]["token"].startswith("lock_")
    assert payload["locks"][0]["token"] == artifact["locks"][0]["token"]


def test_component_optimization_artifact_write_failure_leaves_candidates_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("strategy artifact write failed")

    monkeypatch.setattr(strategy_runs, "_write_strategy_artifact", fail_write)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "artifact-failure"]) == 10

    payload = _last_json_line(capsys.readouterr().err)
    manifest = json.loads((tmp_path / "runs" / "artifact-failure" / "manifest.json").read_text())
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"

    assert payload["error"]["category"] == "execution_failure"
    assert manifest["run"]["status"] == RunStatus.FAILED
    with CandidateStore(store_path) as store:
        assert store.top_candidates_by_run("artifact-failure", limit=1) == []


def test_component_optimization_completion_failure_leaves_lock_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from research.aegis_research.provenance.recorder import RunRecorder

    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    def fail_completion(self: RunRecorder) -> None:
        raise OSError("run completion failed")

    monkeypatch.setattr(RunRecorder, "mark_run_completed", fail_completion)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "completion-failure"]) == 10

    capsys.readouterr()
    artifact = json.loads(
        (tmp_path / "runs" / "completion-failure" / "strategy_run.json").read_text()
    )
    manifest = json.loads((tmp_path / "runs" / "completion-failure" / "manifest.json").read_text())
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"

    assert manifest["run"]["status"] == RunStatus.FAILED
    with (
        CandidateStore(store_path) as store,
        pytest.raises(CandidateStoreError, match="unknown lock token"),
    ):
        store.params_by_lock_token(artifact["locks"][0]["token"])


def test_component_optimization_activation_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    def fail_activation(self: CandidateStore, run_id: str) -> None:
        raise CandidateStoreError(f"activation failed for {run_id}")

    monkeypatch.setattr(CandidateStore, "activate_run", fail_activation)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "activation-failure"]) == 10

    payload = _last_json_line(capsys.readouterr().err)
    artifact = json.loads(
        (tmp_path / "runs" / "activation-failure" / "strategy_run.json").read_text()
    )
    manifest = json.loads((tmp_path / "runs" / "activation-failure" / "manifest.json").read_text())
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"

    assert "candidate_store_activation_failed" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    with (
        CandidateStore(store_path) as store,
        pytest.raises(CandidateStoreError, match="unknown lock token"),
    ):
        store.params_by_lock_token(artifact["locks"][0]["token"])


def test_component_optimization_resolves_lock_id_as_fixed_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "source-run"]) == 0
    source_artifact = json.loads(
        (tmp_path / "runs" / "source-run" / "strategy_run.json").read_text()
    )
    lock_id = source_artifact["locks"][0]["token"]

    locked_config_path = _write_run_config(
        tmp_path,
        strategy={"id": "demo.ma_opt", "lock_id": lock_id},
    )

    assert cli.main(["run", str(locked_config_path), "--json", "--run-id", "locked-run"]) == 0

    capsys.readouterr()
    locked_artifact = json.loads(
        (tmp_path / "runs" / "locked-run" / "strategy_run.json").read_text()
    )

    assert locked_artifact["strategy"]["param_mode"] == "locked"
    assert locked_artifact["strategy"]["fixed_params"] == source_artifact["locks"][0]["params"]
    assert locked_artifact["resolved_locks"][0]["reference_kind"] == "lock_id"
    assert locked_artifact["execution"]["sampled_rows"]["index_names"] == [FIXED_CANDIDATE_PARAM]
    assert len(locked_artifact["candidates"]) == 1


def test_component_optimization_resolves_candidate_id_pin_as_fixed_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_parameterized_strategy_component(tmp_path / "research/components/strategies/ma_opt.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "candidate-source"]) == 0
    source_artifact = json.loads(
        (tmp_path / "runs" / "candidate-source" / "strategy_run.json").read_text()
    )
    pinned_row = source_artifact["leaderboard"]["rows"][1]
    fast_key = component_param_key("strategies", "demo.ma_opt", "strategy", "fast_window")
    slow_key = component_param_key("strategies", "demo.ma_opt", "strategy", "slow_window")
    expected_params = {
        "fast_window": pinned_row["params"][fast_key],
        "slow_window": pinned_row["params"][slow_key],
    }

    pinned_config_path = _write_run_config(
        tmp_path,
        strategy={
            "id": "demo.ma_opt",
            "candidate_id": pinned_row["candidate_key"],
            "run_id": "candidate-source",
        },
    )

    assert cli.main(["run", str(pinned_config_path), "--json", "--run-id", "candidate-pin"]) == 0

    capsys.readouterr()
    pinned_artifact = json.loads(
        (tmp_path / "runs" / "candidate-pin" / "strategy_run.json").read_text()
    )

    assert pinned_artifact["strategy"]["param_mode"] == "locked"
    assert pinned_artifact["strategy"]["fixed_params"] == expected_params
    assert pinned_artifact["resolved_locks"][0]["reference_kind"] == "candidate_id"
    assert pinned_artifact["resolved_locks"][0]["candidate_key"] == pinned_row["candidate_key"]


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
    assert (
        "component optimization failed intentionally"
        in manifest["stages"][-1]["diagnostic"]["message"]
    )


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
    assert (
        manifest["evidence"]["optimization"]["preflight_failure"]["error_type"] == "PreflightError"
    )
    assert (
        "exceed optimization.split.max_estimated_output_cells"
        in manifest["stages"][-1]["diagnostic"]["message"]
    )


def _write_run_config(
    tmp_path: Path,
    *,
    strategy: dict[str, object] | None = None,
    strategy_id: str = "demo.ma_opt",
    candidate_grid: dict[str, object] | None = None,
    optimization: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            _run_config_payload(
                strategy=strategy or {"id": strategy_id},
                indicators=[],
                candidate_grid=candidate_grid,
                optimization=optimization or {"search": "grid", "split": _rolling_split_config()},
            ),
            sort_keys=False,
        )
    )
    return path


def _last_json_line(text: str) -> dict[str, object]:
    for line in reversed(text.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"no JSON object line found in stream: {text!r}")


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
            "symbols": ["SYN", "SYN2"],
            "rows": 80,
            "arrays": ["OHLCV"],
        },
        "portfolio": {"target_exposure_cap": 1.0},
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
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.ma_opt', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['fast_window', 'slow_window'], "
        "'output_name': 'active', "
        "'defaults': {'fast_window': 2, 'slow_window': 5}, "
        "'param_space_callable': 'param_space', 'owns_portfolio': False, "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% parameter space\n"
        "def param_space():\n"
        f"    return {{'fast_window': vbt.Param({fast_values!r}), "
        f"'slow_window': vbt.Param({slow_values!r})}}\n"
        "\n# %% main compute\n"
        "def run(inputs, fast_window, slow_window):\n"
        '    """Emit an active allocation frame from fixed MA crossover params."""\n'
        + (
            "    raise RuntimeError('component should not execute after preflight failure')\n"
            if fail_if_executed
            else ""
        )
        + "    close = inputs.data.feature('Close')\n"
        "    fast = close.rolling(int(fast_window), min_periods=1).mean()\n"
        "    slow = close.rolling(int(slow_window), min_periods=1).mean()\n"
        "    selected = fast.gt(slow).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from MA crossover params."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    fast_windows = param_lists['fast_window']\n"
        "    slow_windows = param_lists['slow_window']\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    close_arr = close.values\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        fw, sw = int(fast_windows[i]), int(slow_windows[i])\n"
        "        fast = pd.DataFrame(close_arr).rolling(fw, min_periods=1).mean().values\n"
        "        slow = pd.DataFrame(close_arr).rolling(sw, min_periods=1).mean().values\n"
        "        selected = fast > slow\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
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
        "'output_name': 'active', 'owns_portfolio': False, "
        "'defaults': {'window': 2}, 'param_space_callable': 'param_space', "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2])}\n"
        "\n# %% main compute\n"
        "def run(inputs, window):\n"
        '    """Raise a deterministic execution failure."""\n'
        "    raise RuntimeError('component optimization failed intentionally')\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Raise a deterministic execution failure."""\n'
        "    raise RuntimeError('component optimization failed intentionally')\n"
    )
