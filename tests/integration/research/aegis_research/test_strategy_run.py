from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.strategy_runs import StrategyInputs, validate_strategy_output


def test_strategy_output_boundary_rejects_portfolio_fields() -> None:
    close = _frame()
    inputs = StrategyInputs(
        data=MarketDataBundle(features={"Close": close}, loaded_features=("Close",)),
        indicators={},
        metadata={},
    )
    output = {
        "entries": close > 1,
        "exits": close < 1,
        "size": 0.5,
    }

    with pytest.raises(ValueError, match="portfolio"):
        validate_strategy_output(output, inputs)


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
    assert "removed from the forward run contract" in payload["error"]["message"]
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
        indicators=[{"source": "component", "ids": ["demo.ma"]}],
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


def test_strategy_run_rejects_partial_leaderboard_side_path_without_optimization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "partial-run"]) == 6
    _assert_missing_optimization_config_error(capsys, tmp_path, "partial-run")


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
        indicators=[{"source": "component", "ids": ["demo.ma"]}],
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
                    "symbols": ["SYN"],
                    "rows": 80,
                    "arrays": arrays or ["OHLCV"],
                }
                | (data or {}),
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": "component", "id": strategy_id},
                "indicators": indicators or [{"source": "component", "ids": "all"}],
                "ranking": {"metric": "total_return", "direction": "desc"},
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
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.cross', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'signal_outputs': ['entries', 'exits'], 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Generate fixed moving-average crossover entry and exit signals."""\n'
        "    close = bundle.data.feature('Close')\n"
        "    entries = close > close.rolling(3).mean()\n"
        "    exits = close < close.rolling(3).mean()\n"
        "    return {'entries': entries.fillna(False), 'exits': exits.fillna(False)}\n"
    )


def _write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used by strategy-run integration tests.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.ma', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], 'output_names': ['ma']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute the fixed moving-average indicator."""\n'
        "    return data.feature('Close').rolling(2).mean().bfill()\n"
    )


def _write_misaligned_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used to test bar-alignment validation.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.ma', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['ma']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Return a deliberately misaligned indicator fixture."""\n'
        "    result = data.feature('Close').copy()\n"
        "    result.columns = ['OTHER']\n"
        "    return result\n"
    )


def _write_named_indicator_component(path: Path, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture used by strategy-run integration tests.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        f"'family': 'indicators', 'id': {component_id!r}, 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['value']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute a fixed moving-average indicator fixture."""\n'
        "    return data.feature('Close').rolling(2).mean().bfill()\n"
    )


def _write_indicator_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture consuming the fixed moving-average indicator output.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.uses_ma', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'signal_outputs': ['entries', 'exits'], 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Generate signals from the selected moving-average indicator."""\n'
        "    ma = bundle.indicators['demo.ma']\n"
        "    close = bundle.data.feature('Close')\n"
        "    entries = close > ma\n"
        "    exits = close < ma\n"
        "    return {'entries': entries.fillna(False), 'exits': exits.fillna(False)}\n"
    )


def _write_two_indicator_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture consuming fixed fast and slow indicator outputs.\n"
        "# Source: synthetic Close data supplied by the run config.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.uses_all', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'signal_outputs': ['entries', 'exits'], 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Generate signals from fixed fast and slow indicator outputs."""\n'
        "    fast = bundle.indicators['demo.fast']\n"
        "    slow = bundle.indicators['demo.slow']\n"
        "    entries = fast >= slow\n"
        "    exits = fast < slow\n"
        "    return {'entries': entries.fillna(False), 'exits': exits.fillna(False)}\n"
    )


def _frame():
    import pandas as pd

    return pd.DataFrame({"SYN": [1.0, 2.0, 1.5]}, index=pd.date_range("2020-01-01", periods=3))
