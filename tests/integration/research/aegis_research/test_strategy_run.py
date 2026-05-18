from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.config import CONFIG_SCHEMA_VERSION
from research.aegis_research.provenance.manifest import RunStatus
from research.aegis_research.strategy_runs import StrategyInputBundle, validate_strategy_output
from tests.support.research.aegis_research.model_plugin_fixtures import model_config_dict


def test_strategy_output_boundary_rejects_portfolio_fields() -> None:
    bundle = StrategyInputBundle(
        close=_frame(),
        indicators={},
        params={},
        metadata={},
    )
    output = {
        "entries": bundle.close > 1,
        "exits": bundle.close < 1,
        "size": 0.5,
    }

    with pytest.raises(ValueError, match="portfolio"):
        validate_strategy_output(output, bundle)


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
    assert "aerd train" in message
    assert not (tmp_path / "runs" / "should-not-exist").exists()


def _write_run_config(tmp_path: Path) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "lane": "run",
                "name": "strategy_run_contract",
                "output_dir": "runs",
                "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 80},
                "portfolio": {"entry_budget": 1.0},
                "strategy": {"source": "component", "id": "demo.cross"},
                "indicator_refs": [{"source": "component", "id": "all"}],
                "ranking": {"metric": "total_return_pct", "direction": "desc"},
            },
            sort_keys=False,
        )
    )
    return path


def _write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.cross', 'version': '1.0.0', "
        "'signal_outputs': ['entries', 'exits'], 'owns_portfolio': False}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run(bundle):\n"
        "    entries = bundle.close > bundle.close.rolling(3).mean()\n"
        "    exits = bundle.close < bundle.close.rolling(3).mean()\n"
        "    return {'entries': entries.fillna(False), 'exits': exits.fillna(False)}\n"
    )


def _frame():
    import pandas as pd

    return pd.DataFrame({"SYN": [1.0, 2.0, 1.5]}, index=pd.date_range("2020-01-01", periods=3))
