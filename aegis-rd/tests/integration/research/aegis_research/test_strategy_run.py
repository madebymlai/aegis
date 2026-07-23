from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from tests.support.research.aegis_research.market_data_fixtures import (
    DEFAULT_INSTRUMENT_ID_VALUES,
    native_data_config_payload,
    seed_catalog_ohlcv,
)


def test_strategy_run_cli_rejects_component_strategy_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--run-id", "strategy-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "strategy-run")


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

    assert cli.main(["run", str(config_path), "--run-id", "indicator-run"]) == 6
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

    assert cli.main(["run", str(config_path), "--run-id", "all-indicators-run"]) == 6
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

    assert cli.main(["run", str(config_path), "--run-id", "bad-strategy-arrays"]) == 6

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
        optimization={"search": "grid", "observation_block_bars": 20},
    )

    assert cli.main(["run", str(config_path), "--run-id", "component-opt"]) == 0

    payload = json.loads(capsys.readouterr().out)
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"
    with CandidateStore(store_path) as store:
        best_key = store.candidate_key_for_role("component-opt", "best")
        stored = store.candidate_by_key(best_key, run_id="component-opt")
    source = stored["provenance"]["source"]

    assert payload["status"] == "success"
    assert not (tmp_path / "runs" / "component-opt.json").exists()
    assert source["strategy"]["family"] == "strategies"
    assert source["strategy"]["id"] == "demo.cross"
    assert list(stored["params"]) == [FIXED_CANDIDATE_PARAM]
    assert [candidate["role"] for candidate in payload["candidates"]] == [
        "best",
        "median",
        "worst",
    ]
    assert payload["optimization"]["protocol"] == "continuous_future_in_past"
    assert payload["optimization"]["observation_block_bars"] == 20
    assert payload["optimization"]["total"] == 1
    assert len(payload["candidates"]) == 3
    assert len({candidate["candidate_key"] for candidate in payload["candidates"]}) == 1


def test_strategy_run_always_emits_json_with_lock_handles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # aegis-rd-gg3.3: aerd run always emits JSON without --json flag;
    # lock handles are payload data (best = bare run_id, others carry :role).
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(
        tmp_path,
        optimization={"search": "grid", "observation_block_bars": 20},
    )

    assert cli.main(["run", str(config_path), "--run-id", "lock-handle-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["command"] == "run"
    # Lock handles in the JSON payload
    locks = {c["role"]: c["lock"] for c in payload["candidates"]}
    assert locks["best"] == "lock-handle-run"
    assert locks["median"] == "lock-handle-run:median"
    assert locks["worst"] == "lock-handle-run:worst"
    assert "selection" not in payload
    assert payload["run"] == {"id": "lock-handle-run"}
    assert not (tmp_path / "runs" / "lock-handle-run.json").exists()


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
        optimization={"search": "grid", "observation_block_bars": 20},
    )

    assert cli.main(["run", str(config_path), "--run-id", "component-locks"]) == 0

    payload = json.loads(capsys.readouterr().out)
    store_path = tmp_path / "runs" / ".candidate_store" / "candidates.sqlite3"
    with CandidateStore(store_path) as store:
        best_key = store.candidate_key_for_role("component-locks", "best")
        source = store.candidate_by_key(best_key, run_id="component-locks")["provenance"]["source"]

    assert not (tmp_path / "runs" / "component-locks.json").exists()
    assert "locks" not in payload

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

    assert cli.main(["run", str(config_path), "--run-id", "bad-data"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "bad-data")


def test_strategy_run_rejects_fixed_strategy_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--run-id", "fixed-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "fixed-run")


def test_strategy_run_reports_config_validation_failure(
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
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
        },
    )

    assert cli.main(["run", str(config_path), "--run-id", "secret-run"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "optimization: Field required" in payload["error"]["message"]
    assert "<redacted>" not in output.err


def test_strategy_run_maps_component_registry_errors_to_config_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/one.py")
    _write_strategy_component(tmp_path / "research/components/strategies/two.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--run-id", "bad-registry"]) == 6

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

    assert cli.main(["run", str(config_path), "--run-id", "bad-indicator"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "bad-indicator")


def test_strategy_run_rejects_interrupt_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--run-id", "interrupted-run"]) == 6
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
                "data": native_data_config_payload(instruments=["SYN.XNAS"]),
                "model": {"source": "plugin", "id": "demo.model"},
                "portfolio": {"entry_budget": 1.0},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    message = json.loads(output.err)["error"]["message"]
    assert "Unexpected keyword argument" in message
    assert "aerd run --train" not in message
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def test_run_rejects_optimization_without_observation_block_bars_before_run_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path, optimization={"search": "grid"})

    assert cli.main(["run", str(config_path), "--run-id", "no-observation-blocks"]) == 6

    output = capsys.readouterr()
    payload = json.loads(output.err)
    assert payload["error"]["category"] == "config_validation"
    assert "optimization.observation_block_bars" in payload["error"]["message"]
    assert not (tmp_path / "runs" / "no-observation-blocks").exists()


def test_run_missing_config_is_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["run", "missing.yaml"]) == 6

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
    assert "optimization: Field required" in payload["error"]["message"]
    assert not (tmp_path / "runs" / run_id).exists()


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_id: str = "demo.cross",
    indicators: list[dict[str, object]] | None = None,
    arrays: list[str] | None = None,
    data: dict[str, object] | None = None,
    optimization: dict[str, object] | None = None,
) -> Path:
    seed_catalog_ohlcv(
        tmp_path / "catalog",
        DEFAULT_INSTRUMENT_ID_VALUES,
        periods=80,
    )
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "strategy_run_contract",
                "output_dir": "runs",
                "data": native_data_config_payload(
                    instruments=DEFAULT_INSTRUMENT_ID_VALUES,
                    arrays=arrays or ["OHLCV"],
                    end="2024-03-21",
                    path=tmp_path / "catalog",
                )
                | (data or {}),
                "portfolio": {"direction": "longonly"},
                "strategy": {"id": strategy_id},
                "indicators": indicators or [],
                "ranking": {"metric": "total_return"},
                **({"optimization": optimization} if optimization is not None else {}),
            },
            sort_keys=False,
        )
    )
    return path


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
        "'output_name': 'active', 'owns_portfolio': False}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit a deterministic active allocation frame from a fixed MA crossover."""\n'
        "    close = bundle.data.array('Close')\n"
        "    selected = close.gt(close.rolling(3).mean()).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from a fixed MA crossover."""\n'
        "    close = inputs.data.array('Close')\n"
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
        "\n# %% causal lookback\n"
        "def lookback():\n"
        '    """Warm up the fixed three-bar moving average."""\n'
        "    return 3\n"
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
        "'defaults': {'window': 2}}\n"
        "\n# %% main compute\n"
        "def run(data, window=2):\n"
        '    """Compute the fixed moving-average indicator."""\n'
        "    return data.array('Close').rolling(int(window)).mean().bfill()\n"
        "\n# %% wide compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        '    """Return wide indicator output."""\n'
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists.get('window', [2] * n_candidates)\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = pd.DataFrame(close.values).rolling(int(w)).mean().bfill().values\n"
        "    return {'ma': result}\n"
        "\n# %% causal lookback\n"
        "def lookback(window=2):\n"
        '    """Warm up the configured moving average."""\n'
        "    return int(window)\n"
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
        "}\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Return a deliberately misaligned indicator fixture."""\n'
        "    result = data.array('Close').copy()\n"
        "    result.columns = ['OTHER']\n"
        "    return result\n"
        "\n# %% wide compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        '    """Return wide output for misaligned fixture."""\n'
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    return {'ma': np.zeros((T, n_candidates * S))}\n"
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
        "}\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute a fixed moving-average indicator fixture."""\n'
        "    return data.array('Close').rolling(2).mean().bfill()\n"
        "\n# %% wide compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        '    """Return wide indicator output."""\n'
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = pd.DataFrame(close.values).rolling(2).mean().bfill().values\n"
        "    return {'value': result}\n"
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
        "'owns_portfolio': False}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit an active allocation frame from the selected MA indicator."""\n'
        "    ma = bundle.indicators['ma']\n"
        "    close = bundle.data.array('Close')\n"
        "    selected = close.gt(ma).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from MA indicator."""\n'
        "    close = inputs.data.array('Close')\n"
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
        "\n# %% causal lookback\n"
        "def lookback():\n"
        '    """The consumed Indicator owns the moving-average warmup."""\n'
        "    return 0\n"
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
        "'output_name': 'active', 'owns_portfolio': False}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Emit an active allocation frame from fast and slow indicator outputs."""\n'
        "    fast = bundle.indicators['demo.fast']\n"
        "    slow = bundle.indicators['demo.slow']\n"
        "    close = bundle.data.array('Close')\n"
        "    selected = fast.ge(slow).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide allocation from fast and slow indicators."""\n'
        "    close = inputs.data.array('Close')\n"
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
