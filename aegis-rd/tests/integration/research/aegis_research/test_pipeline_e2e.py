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
                    "observation_block_bars": 84,
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
    optimization_evidence = manifest["evidence"]["optimization"]
    assert optimization_evidence["source"]["schema_version"] == "component_optimization_source.v2"
    assert optimization_evidence["schema_version"] == "optimization_route.v2"
    assert artifact["schema_version"] == "optimization_artifact.v2"
    assert "selection" in artifact
    assert "split" not in artifact
    execution = artifact["execution"]
    assert execution["schema_version"] == "continuous_selection_evidence.v1"
    serialized_public_evidence = json.dumps(
        {"execution": execution, "candidates": artifact["candidates"]}
    ).lower()
    assert "held_out" not in serialized_public_evidence
    assert "optimism_gap" not in serialized_public_evidence
    assert "friedman" not in serialized_public_evidence
    assert "omnibus" not in serialized_public_evidence
    assert set(execution["raw_metric_matrices"]) == {
        "max_dd",
        "sharpe_ratio",
        "total_fees_paid",
        "total_return",
        "total_trades",
        "win_rate",
    }
    best, median, worst = artifact["candidates"]
    assert best["role"] == "best"
    assert median["role"] == "median"
    assert worst["role"] == "worst"
    assert best["schema_version"] == "candidate_eval_row.v3"
    assert median["schema_version"] == "candidate_eval_row.v3"
    assert worst["schema_version"] == "candidate_eval_row.v3"
    assert best["identity"]["schema_version"] == "candidate_identity.v5"
    assert median["identity"]["schema_version"] == "candidate_identity.v5"
    assert worst["identity"]["schema_version"] == "candidate_identity.v5"
    assert (
        artifact["candidate_store"]["provenance"]["schema_version"]
        == "candidate_store_provenance.v2"
    )
