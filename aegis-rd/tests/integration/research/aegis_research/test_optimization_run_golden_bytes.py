"""Golden-bytes oracle: a full optimization Run's persisted Manifest is byte-stable.

Executes a complete synthetic Run (fixture Components, pinned seed, pinned
run-id) through the real CLI and compares the persisted ``manifest.json`` —
volatile fields masked, re-serialized in Canonical Form — byte-for-byte
against a committed golden. Any unexpected movement in config evidence,
optimization evidence, stage outcomes, artifact hashes, or candidate rows
fails this test (aegis-rd-0vh; ADR-0003/0004 golden-bytes style).

Regenerate the golden deliberately after an intended change::

    AERD_UPDATE_GOLDENS=1 uv run pytest tests/integration/research/aegis_research/test_optimization_run_golden_bytes.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from research.aegis_research import cli
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
from tests.support.research.aegis_research.golden import (
    assert_matches_golden,
    masked_canonical_manifest,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    ETF_INSTRUMENT_ID_VALUES,
    native_data_config_payload,
    seed_catalog_ohlcv,
)

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
_GOLDEN_PATH = _FIXTURES / "goldens" / "optimization_run_manifest.json"
_RUN_ID = "golden-bytes-oracle"

def test_optimization_run_manifest_matches_golden_bytes(tmp_path, monkeypatch) -> None:
    _install_fixture_components(tmp_path)
    seed_catalog_ohlcv(
        tmp_path / "catalog",
        ETF_INSTRUMENT_ID_VALUES,
        periods=1008,
        seed=42,
    )
    config_path = _write_oracle_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["run", str(config_path), "--run-id", _RUN_ID]) == 0

    run_dir = tmp_path / "runs" / _RUN_ID
    manifest = json.loads((run_dir / "manifest.json").read_text())
    source_evidence = manifest["evidence"]["optimization"]["source"]

    assert source_evidence["schema_version"] == "component_optimization_source.v2"
    assert_matches_golden(masked_canonical_manifest(manifest), _GOLDEN_PATH)


def _install_fixture_components(tmp_path: Path) -> None:
    """Copy the committed fixture Components into the discovery root."""
    for family in ("indicators", "strategies"):
        target = tmp_path / "research" / "components" / family
        target.mkdir(parents=True)
        for source in sorted((_FIXTURES / "components" / family).glob("*.py")):
            shutil.copy(source, target / source.name)


def _write_oracle_config(tmp_path: Path) -> Path:
    """A fully deterministic optimization Run config.

    Both Indicators are frozen via ``params`` (values taken from their declared
    param spaces, momentum values verbatim from the lock fixture config), so the
    Strategy's 30-combo space is the entire grid. The temp Nautilus catalog is
    seeded with 1008 rows = two rolling 504-row Splits at the momentum
    Indicator's 200-bar maximum lookback.
    """
    path = tmp_path / "golden_oracle.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "golden_bytes_oracle",
                "output_dir": "runs",
                "data": native_data_config_payload(
                    instruments=ETF_INSTRUMENT_ID_VALUES,
                    end="2026-10-05",
                    path="catalog",
                ),
                "portfolio": {
                    "gross_cap": 1.0,
                    "direction": "longonly",
                    "fees": 0.0005,
                    "slippage": 0.0005,
                },
                "strategy": {"id": "tests.momentum_rotator"},
                "indicators": [
                    {
                        "id": "tests.momentum_score",
                        "params": {
                            "h1": 15,
                            "h2": 42,
                            "h3": 100,
                            "h4": 200,
                            "w1": 8.0,
                            "w2": 4.0,
                            "w3": 3.0,
                            "w4": 2.0,
                        },
                    },
                    {"id": "tests.realized_vol", "params": {"window": 20}},
                ],
                "ranking": {"metric": "sharpe_ratio"},
                "optimization": {
                    "search": "grid",
                    "split": {
                        "method": "from_rolling",
                        "params": {"length": 504, "offset": 0, "split": 0.5},
                        "max_splits": 10,
                        "max_estimated_output_cells": 1_000_000_000,
                        "max_public_artifact_bytes": 20_000_000,
                    },
                },
            },
            sort_keys=False,
        )
    )
    return path
