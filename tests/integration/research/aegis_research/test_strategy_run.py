from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.optimization.component_source import FIXED_CANDIDATE_PARAM


def test_strategy_run_cli_rejects_component_strategy_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "strategy-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "strategy-run")


def test_strategy_run_cli_rejects_component_strategy_with_top_level_rolling_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path, split=_rolling_split_config())

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-rolling"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "component-rolling")


def test_strategy_run_cli_rejects_component_strategy_with_top_level_purged_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path, split=_purged_kfold_split_config())

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-purged"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "component-purged")


def test_strategy_run_rejects_candidate_grid_before_split_execution_budget_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")

    config_path = _write_run_config(
        tmp_path,
        split=_rolling_split_config(),
        candidate_grid={"max_estimated_cells": 1},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "split-over-budget"]) == 6
    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "candidate_grid" in payload["error"]["message"]
    assert "unknown field" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "split-over-budget").exists()


def test_strategy_run_rejects_component_split_failure_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")

    config_path = _write_run_config(tmp_path, split=_rolling_split_config())

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-split-fails"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "component-split-fails")


def test_strategy_run_rejects_component_indicator_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_indicator_component(tmp_path / "research/components/indicators/ma.py")
    _write_indicator_strategy_component(tmp_path / "research/components/strategies/uses_ma.py")
    config_path = _write_run_config(
        tmp_path,
        strategy_id="demo.uses_ma",
        indicators=[{"id": "demo.ma", "params": {"window": 2}}],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "indicator-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "indicator-run")


def test_strategy_run_rejects_all_component_indicator_expansion_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_named_indicator_component(
        tmp_path / "research/components/indicators/fast.py", "demo.fast"
    )
    _write_named_indicator_component(
        tmp_path / "research/components/indicators/slow.py", "demo.slow"
    )
    _write_two_indicator_strategy_component(tmp_path / "research/components/strategies/uses_all.py")
    config_path = _write_run_config(tmp_path, strategy_id="demo.uses_all")

    assert cli.main(["run", str(config_path), "--json", "--run-id", "all-indicators-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "all-indicators-run")


def test_strategy_run_rejects_component_input_array_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    strategy_path = tmp_path / "research/components/strategies/cross.py"
    strategy_path.write_text(strategy_path.read_text().replace("['Close']", "['FundingRate']"))
    config_path = _write_run_config(tmp_path, arrays=["Close", "Open"])

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-strategy-arrays"]) == 6

    _assert_missing_optimization_config_error(capsys, tmp_path, "bad-strategy-arrays")


def test_strategy_run_executes_fixed_component_through_native_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(
        tmp_path,
        optimization={"search": "grid", "split": _rolling_split_config()},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-opt"]) == 0

    payload = json.loads(capsys.readouterr().out)
    artifact = json.loads((tmp_path / "runs" / "component-opt" / "strategy_run.json").read_text())

    assert payload["status"] == "success"
    assert artifact["strategy"]["family"] == "strategies"
    assert artifact["strategy"]["id"] == "demo.cross"
    assert [shape["name"] for shape in artifact["preflight"]["param_shapes"]] == [
        FIXED_CANDIDATE_PARAM
    ]
    assert [candidate["role"] for candidate in artifact["candidates"]] == [
        "best",
        "median",
        "worst",
    ]
    ranking_metric = artifact["ranking"]["metric"]
    assert "held_out_warning" in payload["optimization"]
    # Completion threads the *exact* exclusion accounting from the execution
    # Evidence (never a preflight estimate) into the optimization summary, so the
    # terminal can render the researched/total ratio.
    execution = artifact["execution"]
    assert payload["optimization"]["total"] == execution["total"]
    assert payload["optimization"]["excluded_invalid"] == execution["excluded_invalid"]
    assert payload["optimization"]["excluded_degenerate"] == execution["excluded_degenerate"]
    for summary, candidate in zip(payload["candidates"], artifact["candidates"], strict=True):
        assert summary["role"] == candidate["role"]
        assert summary["rank"] == candidate["rank"]
        assert summary["candidate_key"] == candidate["candidate_key"]
        assert summary["params"] == candidate["params"]
        assert summary["score"] == candidate["score"]
        assert summary["metrics"] == candidate["metrics"]
        assert summary["selection_metrics"] == candidate["selection_metrics"]
        assert summary["held_out_metrics"] == candidate["held_out_metrics"]
        # held-out aggregate is serialized in the artifact, as prominent as `metrics`.
        assert summary["held_out_metrics_mean"] == candidate["held_out_metrics_mean"]
        headline = summary["held_out_headline"]
        assert headline["metric"] == ranking_metric
        assert headline["held_out"] == candidate["held_out_metrics_mean"].get(ranking_metric)
        assert headline["selection"] == candidate["metrics"].get(ranking_metric)
        if headline["held_out"] is not None and headline["selection"] is not None:
            assert headline["gap"] == pytest.approx(headline["selection"] - headline["held_out"])
    assert len(artifact["candidates"]) == 3
    assert len({candidate["candidate_key"] for candidate in artifact["candidates"]}) == 1


def test_strategy_run_prints_copy_paste_lock_handles_in_human_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # aegis-rd-6ie: a successful run hands the user copy-paste lock: handles (best is the
    # bare run_id; median/worst carry :role) plus a run_id + candidate-store footer.
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(
        tmp_path,
        optimization={"search": "grid", "split": _rolling_split_config()},
    )

    assert cli.main(["run", str(config_path), "--run-id", "lock-handle-run"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert any(line.rstrip().endswith("lock: lock-handle-run") for line in lines)
    assert any(line.rstrip().endswith("lock: lock-handle-run:median") for line in lines)
    assert any(line.rstrip().endswith("lock: lock-handle-run:worst") for line in lines)
    assert any(line == "run_id: lock-handle-run" for line in lines)
    assert any(line.startswith("candidate store:") for line in lines)


def test_strategy_run_retires_the_locks_section_and_honors_inline_params(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ADR-0006 (aegis-rd-396.4): publishing no longer mints per-Component lock records;
    # the LOCKS Evidence section and the artifact "locks" key are retired. Inline
    # values-only params: still freeze a single Component while the rest optimize.
    monkeypatch.chdir(tmp_path)
    _write_indicator_component(tmp_path / "research/components/indicators/ma.py")
    _write_indicator_strategy_component(tmp_path / "research/components/strategies/uses_ma.py")
    config_path = _write_run_config(
        tmp_path,
        strategy_id="demo.uses_ma",
        indicators=[{"id": "demo.ma", "params": {"window": 2}}],
        optimization={"search": "grid", "split": _rolling_split_config()},
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "component-locks"]) == 0

    capsys.readouterr()
    artifact = json.loads((tmp_path / "runs" / "component-locks" / "strategy_run.json").read_text())
    manifest = json.loads((tmp_path / "runs" / "component-locks" / "manifest.json").read_text())
    source = manifest["evidence"]["optimization"]["source"]

    assert "locks" not in artifact
    assert "resolved_locks" not in artifact
    assert "locks" not in manifest["evidence"]["optimization"]

    indicator = next(ind for ind in source["indicators"] if ind["id"] == "demo.ma")
    assert indicator["fixed_params"] == {"window": 2}
    assert indicator["param_mode"] == "fixed"


def test_strategy_run_rejects_data_quality_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-data"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "bad-data")


def test_strategy_run_rejects_fixed_strategy_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "fixed-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "fixed-run")


def test_strategy_run_redacts_known_config_secrets_on_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REMOTE_PASSWORD", "hunter2")
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(
        tmp_path,
        data={
            "source": "yf",
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"password": {"env": "REMOTE_PASSWORD"}},
        },
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "secret-run"]) == 6

    output = capsys.readouterr()
    assert "hunter2" not in output.err
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "fixed/non-optimized strategy runs are removed" in payload["error"]["message"]


def test_strategy_run_maps_component_registry_errors_to_config_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/one.py")
    _write_strategy_component(tmp_path / "research/components/strategies/two.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-registry"]) == 6

    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["category"] == "config_validation"
    assert "duplicate component id" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "bad-registry").exists()


def test_strategy_run_rejects_indicator_symbol_mismatch_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_misaligned_indicator_component(tmp_path / "research/components/indicators/bad.py")
    _write_indicator_strategy_component(tmp_path / "research/components/strategies/uses_ma.py")
    config_path = _write_run_config(
        tmp_path,
        strategy_id="demo.uses_ma",
        indicators=[{"id": "demo.ma", "params": {"window": 2}}],
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-indicator"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "bad-indicator")


def test_strategy_run_rejects_interrupt_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "interrupted-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "interrupted-run")


def test_run_rejects_removed_model_training_config_without_train_guidance(
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
                "name": "ml_config",
                "output_dir": "runs",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN"],
                    "rows": 120,
                    "arrays": ["OHLCV"],
                },
                "model": {"source": "plugin", "id": "demo.model"},
                "portfolio": {"entry_budget": 1.0},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    message = json.loads(output.err)["error"]["message"]
    assert "single run config contract" in message
    assert "aerd run --train" not in message
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_run_rejects_optimization_without_nested_split_before_run_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path, optimization={"search": "grid"})

    assert cli.main(["run", str(config_path), "--json", "--run-id", "no-optimization-split"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "optimization.split" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "no-optimization-split").exists()


def test_run_missing_config_is_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["run", "missing.yaml", "--json"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"


def _assert_missing_optimization_config_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    run_id: str,
) -> None:
    output = capsys.readouterr()
    assert output.out == ""
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "optimization" in payload["error"]["message"]
    assert "fixed/non-optimized strategy runs are removed" in payload["error"]["message"]
    assert not (tmp_path / "runs" / run_id).exists()


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_id: str = "demo.cross",
    indicators: list[dict[str, object]] | None = None,
    arrays: list[str] | None = None,
    data: dict[str, object] | None = None,
    split: dict[str, object] | None = None,
    candidate_grid: dict[str, object] | None = None,
    optimization: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "strategy_run_contract",
                "output_dir": "runs",
                "data": {
                    "source": "synthetic",
                    "symbols": ["SYN", "SYN2"],
                    "rows": 80,
                    "arrays": arrays or ["OHLCV"],
                }
                | (data or {}),
                "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
                "strategy": {"id": strategy_id},
                "indicators": indicators or [],
                "ranking": {"metric": "total_return"},
                **({"split": split} if split is not None else {}),
                **({"candidate_grid": candidate_grid} if candidate_grid is not None else {}),
                **({"optimization": optimization} if optimization is not None else {}),
            },
            sort_keys=False,
        )
    )
    return path


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


def _purged_kfold_split_config() -> dict[str, object]:
    return {
        "method": "from_purged_kfold",
        "params": {"n_folds": 3, "n_test_folds": 1},
        "max_splits": 5,
    }


def _write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture used by run integration tests.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.cross', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'output_name': 'active', 'owns_portfolio': False, 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit a deterministic active allocation frame from a fixed MA crossover."""\n'
        "    close = bundle.data.feature('Close')\n"
        "    selected = close.gt(close.rolling(3).mean()).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from a fixed MA crossover."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    close_arr = close.values\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    ma3 = pd.DataFrame(close_arr).rolling(3, min_periods=1).mean().values\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        selected = close_arr > ma3\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )


def _write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used by strategy-run integration tests.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.ma', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], 'output_names': ['ma'], "
        "'defaults': {'window': 2}, 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data, window=2):\n"
        '    """Compute the fixed moving-average indicator."""\n'
        "    return data.feature('Close').rolling(int(window)).mean().bfill()\n"
        "\n# %% wide compute\n"
        "def run_wide(data, *, n_candidates, **param_lists):\n"
        '    """Return wide indicator output."""\n'
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists.get('window', [2] * n_candidates)\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = pd.DataFrame(close.values).rolling(int(w)).mean().bfill().values\n"
        "    return result\n"
    )


def _write_misaligned_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used to test bar-alignment validation.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.ma', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['ma'], "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Return a deliberately misaligned indicator fixture."""\n'
        "    result = data.feature('Close').copy()\n"
        "    result.columns = ['OTHER']\n"
        "    return result\n"
        "\n# %% wide compute\n"
        "def run_wide(data, *, n_candidates, **param_lists):\n"
        '    """Return wide output for misaligned fixture."""\n'
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    return np.zeros((T, n_candidates * S))\n"
    )


def _write_named_indicator_component(path: Path, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used by strategy-run integration tests.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        f"'family': 'indicators', 'id': {component_id!r}, 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['value'], "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute a fixed moving-average indicator fixture."""\n'
        "    return data.feature('Close').rolling(2).mean().bfill()\n"
        "\n# %% wide compute\n"
        "def run_wide(data, *, n_candidates, **param_lists):\n"
        '    """Return wide indicator output."""\n'
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = pd.DataFrame(close.values).rolling(2).mean().bfill().values\n"
        "    return result\n"
    )


def _write_indicator_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture consuming the fixed moving-average indicator output.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.uses_ma', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'output_name': 'active', 'consumes_outputs': ['ma'], "
        "'owns_portfolio': False, 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit an active allocation frame from the selected MA indicator."""\n'
        "    ma = bundle.indicators['ma']\n"
        "    close = bundle.data.feature('Close')\n"
        "    selected = close.gt(ma).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from MA indicator."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    ma_arr = inputs.indicators['ma']\n"
        "    close_arr = close.values\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        selected = close_arr > ma_arr[:, cols]\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )


def _write_two_indicator_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture consuming fixed fast and slow indicator outputs.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.uses_all', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'output_name': 'active', 'owns_portfolio': False, 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit an active allocation frame from fast and slow indicator outputs."""\n'
        "    fast = bundle.indicators['demo.fast']\n"
        "    slow = bundle.indicators['demo.slow']\n"
        "    close = bundle.data.feature('Close')\n"
        "    selected = fast.ge(slow).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from fast and slow indicators."""\n'
        "    close = inputs.data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        fast = inputs.indicators.get('demo.fast', np.zeros((T, n_candidates * S)))[:, cols]\n"
        "        slow = inputs.indicators.get('demo.slow', np.zeros((T, n_candidates * S)))[:, cols]\n"
        "        selected = fast >= slow\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )
