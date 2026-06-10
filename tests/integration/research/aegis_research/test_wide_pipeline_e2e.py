from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION

COMPONENTS_ROOT = Path(__file__).resolve().parents[4] / "research" / "components"


def test_wide_pipeline_produces_valid_optimization_artifact_with_intree_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "research" / "components"
    shutil.copytree(COMPONENTS_ROOT, dest)

    config_path = tmp_path / "run.yaml"
    config_path.write_text(yaml.safe_dump({
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "wide_pipeline_e2e",
        "output_dir": "runs",
        "data": {
            "source": "synthetic",
            "symbols": ["SPY", "QQQ", "IWM"],
            "rows": 200,
            "arrays": ["OHLCV"],
        },
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {
            "id": "local.e2e.etf_rotation",
            "params": {
                "top_n": 2,
                "rebalance_every": 1,
                "score_entry": 0.0,
                "volatility_ceiling": 2.0,
                "trend_weight": 5.0,
                "momentum_weight": 1.0,
                "volatility_weight": 0.25,
            },
        },
        "indicators": [
            {"id": "local.e2e.trend_ma", "params": {
                "slope_window": 5, "wtype": "exp",
            }},
            {"id": "local.e2e.volatility", "params": {
                "window": 20, "regime_window": 63,
            }},
            {"id": "local.e2e.momentum", "params": {
                "lookback": 63, "smooth_window": 5,
            }},
        ],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 60, "offset": 60, "split": 0.5},
                "max_splits": 2,
            },
        },
    }, sort_keys=False))

    exit_code = cli.main(["run", str(config_path), "--json", "--run-id", "wide-e2e"])

    output = capsys.readouterr()
    assert exit_code == 0, f"CLI failed: {output.err}"

    payload = json.loads(output.out)
    assert payload["status"] == "success"

    artifact_path = tmp_path / "runs" / "wide-e2e" / "strategy_run.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text())

    assert [candidate["role"] for candidate in artifact["candidates"]] == ["best", "median", "worst"]
    assert artifact["candidates"]
    assert len(artifact["candidates"]) > 0

    first_candidate = artifact["candidates"][0]
    param_keys = set(first_candidate["params"])
    for key in param_keys:
        parts = key.split("__")
        assert parts[0] == "component"
