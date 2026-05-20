from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli, strategy_runs
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.market_data.contracts import (
    QUALITY_REJECTED,
    MarketDataBundle,
    MarketDataQuality,
    MarketDataResult,
)
from research.aegis_research.provenance.manifest import RunStatus
from research.aegis_research.strategy_runs import StrategyInputs, validate_strategy_output
from tests.support.research.aegis_research.model_plugin_fixtures import model_config_dict


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


def test_strategy_run_cli_executes_component_strategy_and_writes_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "strategy-run"]) == 0

    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["status"] == "success"
    assert payload["lane"] == "run"
    assert payload["evidence_type"] == "strategy_sweep"
    assert payload["run"]["id"] == "strategy-run"
    assert payload["run"]["status"] == RunStatus.COMPLETED
    assert (tmp_path / "runs" / "strategy-run" / "strategy_run.json").is_file()


def test_strategy_run_passes_component_indicator_sources_to_strategy(
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

    assert cli.main(["run", str(config_path), "--json", "--run-id", "indicator-run"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    artifact = json.loads((tmp_path / "runs" / "indicator-run" / "strategy_run.json").read_text())
    assert payload["status"] == "success"
    assert artifact["indicators"][0]["id"] == "demo.ma"
    assert artifact["leaderboard"]["rows"][0]["indicators"][0]["id"] == "demo.ma"


def test_strategy_run_expands_all_component_indicators_to_strategy(
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

    assert cli.main(["run", str(config_path), "--json", "--run-id", "all-indicators-run"]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    artifact = json.loads(
        (tmp_path / "runs" / "all-indicators-run" / "strategy_run.json").read_text()
    )
    assert payload["status"] == "success"
    assert [item["id"] for item in artifact["indicators"]] == ["demo.fast", "demo.slow"]
    assert [item["id"] for item in artifact["leaderboard"]["rows"][0]["indicators"]] == [
        "demo.fast",
        "demo.slow",
    ]


def test_strategy_run_preflights_component_input_arrays_before_data_load(
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

    payload = json.loads(capsys.readouterr().err)
    manifest = json.loads((tmp_path / "runs" / "bad-strategy-arrays" / "manifest.json").read_text())
    assert payload["error"]["category"] == "config_validation"
    assert "missing required data arrays" in payload["error"]["message"]
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert not (tmp_path / "runs" / "bad-strategy-arrays" / "strategy_run.json").exists()


def test_strategy_run_writes_data_metadata_before_quality_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    def rejected_data(*_args, **_kwargs):
        return MarketDataResult(
            native_data=None,
            metadata={
                "source": "synthetic",
                "quality_state": QUALITY_REJECTED,
                "loaded_arrays": [],
                "unavailable_arrays": ["Close"],
            },
            diagnostics=({"code": "missing_close"},),
            quality=MarketDataQuality(QUALITY_REJECTED, reasons=("Close unavailable",)),
        )

    monkeypatch.setattr(strategy_runs, "load_market_data_result", rejected_data)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-data"]) == 10

    payload = json.loads(capsys.readouterr().err)
    metadata = json.loads((tmp_path / "runs" / "bad-data" / "data_metadata.json").read_text())
    assert payload["run"]["status"] == RunStatus.FAILED
    assert metadata["quality_state"] == QUALITY_REJECTED
    assert metadata["unavailable_arrays"] == ["Close"]


def test_strategy_run_fails_partial_leaderboards_before_writing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    def partial_leaderboard(*_args, **_kwargs):
        return {
            "schema_version": "run_leaderboard.v1",
            "metric": "total_return_pct",
            "direction": "desc",
            "rank_by": "primary_metric",
            "rows": [],
            "failure_samples": [{"variant_id": "failed", "code": "runtime", "message": "boom"}],
            "summary": {
                "attempted": 1,
                "succeeded": 0,
                "failed": 1,
                "excluded": 0,
                "success_ratio": 0.0,
                "partial_leaderboard": True,
                "failure_gating_status": "partial",
            },
        }

    monkeypatch.setattr(strategy_runs, "build_run_leaderboard", partial_leaderboard)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "partial-run"]) == 10

    payload = json.loads(capsys.readouterr().err)
    manifest = json.loads((tmp_path / "runs" / "partial-run" / "manifest.json").read_text())
    assert payload["error"]["category"] == "execution_failure"
    assert manifest["run"]["status"] == RunStatus.FAILED
    assert not (tmp_path / "runs" / "partial-run" / "strategy_run.json").exists()


def test_strategy_run_redacts_known_config_secrets_on_default_run_failure(
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

    def leaking_load(*_args, **_kwargs):
        raise OSError("provider returned hunter2")

    monkeypatch.setattr(strategy_runs, "load_market_data_result", leaking_load)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "secret-run"]) == 10

    output = capsys.readouterr()
    assert "hunter2" not in output.err
    assert json.loads(output.err)["error"]["category"] == "execution_failure"


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


def test_strategy_run_rejects_indicator_symbol_mismatch(
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

    assert cli.main(["run", str(config_path), "--json", "--run-id", "bad-indicator"]) == 10

    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["category"] == "execution_failure"
    assert "misaligned symbols" in payload["error"]["message"]


def test_strategy_run_keyboard_interrupt_marks_manifest_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_strategy_component(tmp_path / "research/components/strategies/cross.py")
    config_path = _write_run_config(tmp_path)

    def interrupting_load(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(strategy_runs, "load_market_data_result", interrupting_load)

    assert cli.main(["run", str(config_path), "--json", "--run-id", "interrupted-run"]) == 130

    output = capsys.readouterr()
    payload = json.loads(output.err)
    manifest = json.loads((tmp_path / "runs" / "interrupted-run" / "manifest.json").read_text())
    assert payload["error"]["category"] == "interrupted"
    assert payload["run"]["status"] == RunStatus.INTERRUPTED
    assert manifest["run"]["status"] == RunStatus.INTERRUPTED


def test_run_rejects_model_training_config_and_points_to_train(
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
                "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120},
                "model": model_config_dict(min_train_samples=1),
                "portfolio": {"entry_budget": 1.0},
            },
            sort_keys=False,
        )
    )

    assert cli.main(["run", str(config_path), "--json", "--run-id", "should-not-exist"]) == 6

    output = capsys.readouterr()
    assert output.out == ""
    message = json.loads(output.err)["error"]["message"]
    assert "aerd run --train" in message
    assert not (tmp_path / "runs" / "should-not-exist").exists()


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


def _write_run_config(
    tmp_path: Path,
    *,
    strategy_id: str = "demo.cross",
    indicators: list[dict[str, object]] | None = None,
    arrays: list[str] | None = None,
    data: dict[str, object] | None = None,
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
                "ranking": {"metric": "total_return_pct", "direction": "desc"},
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
        "'input_names': ['Close'], 'param_names': ['window'], 'output_names': ['ma'], "
        "'default_outputs': ['ma'], "
        "'default_model_features': [{'output': 'ma', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
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
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['ma'], "
        "'default_outputs': ['ma'], "
        "'default_model_features': [{'output': 'ma', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
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
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['value'], "
        "'default_outputs': ['value'], "
        "'default_model_features': [{'output': 'value', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
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
