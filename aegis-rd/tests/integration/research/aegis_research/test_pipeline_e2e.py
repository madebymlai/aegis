from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
from tests.support.research.aegis_research.market_data_fixtures import (
    ETF_INSTRUMENT_ID_VALUES,
    native_data_config_payload,
    seed_catalog_ohlcv,
)

COMPONENTS_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "components"


def test_pipeline_produces_valid_optimization_artifact_with_intree_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    dest = tmp_path / "research" / "components"
    shutil.copytree(COMPONENTS_ROOT, dest)
    seed_catalog_ohlcv(
        tmp_path / "catalog",
        ETF_INSTRUMENT_ID_VALUES,
        periods=300,
    )

    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "pipeline_e2e",
                "output_dir": "runs",
                "data": native_data_config_payload(
                    instruments=ETF_INSTRUMENT_ID_VALUES,
                    end="2024-10-27",
                    path=tmp_path / "catalog",
                ),
                "portfolio": {"direction": "longonly"},
                "strategy": {"id": "tests.momentum_rotator"},
                "indicators": [
                    {
                        "id": "tests.momentum_score",
                        "params": {
                            "h1": 15,
                            "h2": 42,
                            "h3": 63,
                            "h4": 84,
                            "w1": 8.0,
                            "w2": 4.0,
                            "w3": 3.0,
                            "w4": 2.0,
                        },
                    },
                    {"id": "tests.realized_vol", "params": {"window": 20}},
                ],
                "ranking": {"metric": "total_return"},
                "optimization": {
                    "search": "grid",
                    "split": {
                        "method": "from_rolling",
                        "params": {"length": 150, "offset": 0, "split": 0.5},
                        "max_splits": 3,
                    },
                },
            },
            sort_keys=False,
        )
    )

    exit_code = cli.main(["run", str(config_path), "--run-id", "pipeline-e2e"])

    output = capsys.readouterr()
    assert exit_code == 0, f"CLI failed: {output.err}"

    payload = json.loads(output.out)
    assert payload["status"] == "success"

    artifact_path = tmp_path / "runs" / "pipeline-e2e" / "strategy_run.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text())

    manifest_path = tmp_path / "runs" / "pipeline-e2e" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert (
        manifest["evidence"]["optimization"]["source"]["schema_version"]
        == "component_optimization_source.v2"
    )
    assert [candidate["role"] for candidate in artifact["candidates"]] == ["best", "median", "worst"]
    assert artifact["candidates"]
    assert len(artifact["candidates"]) > 0

    first_candidate = artifact["candidates"][0]
    param_keys = set(first_candidate["params"])
    for key in param_keys:
        parts = key.split("__")
        assert parts[0] == "component"
