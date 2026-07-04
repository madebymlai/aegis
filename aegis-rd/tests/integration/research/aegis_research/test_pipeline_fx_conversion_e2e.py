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
    seed_catalog_fx,
    seed_catalog_ohlcv,
)

_FX_PAIR = "EUR/USD.IDEALPRO"

COMPONENTS_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "components"


def _config(*, catalog_path: Path, fx_conversion_cost: float) -> dict:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "fx_conversion_e2e",
        "output_dir": "runs",
        "data": native_data_config_payload(
            instruments=ETF_INSTRUMENT_ID_VALUES,
            end="2024-10-27",
            path=catalog_path,
            exchange=[_FX_PAIR],
        ),
        "portfolio": {
            "gross_cap": 1.0,
            "direction": "longonly",
            "base_currency": "EUR",
            "fx_conversion_cost": fx_conversion_cost,
        },
        "strategy": {"id": "tests.momentum_rotator"},
        "indicators": [
            {
                "id": "tests.momentum_score",
                "params": {
                    "h1": 15, "h2": 42, "h3": 63, "h4": 84,
                    "w1": 8.0, "w2": 4.0, "w3": 3.0, "w4": 2.0,
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
    }


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], config: dict, run_id: str) -> dict:
    config_path = tmp_path / f"{run_id}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    exit_code = cli.main(["run", str(config_path), "--run-id", run_id])
    output = capsys.readouterr()
    assert exit_code == 0, f"CLI failed for {run_id}: {output.err}"
    assert json.loads(output.out)["status"] == "success"
    return json.loads((tmp_path / "runs" / run_id / "strategy_run.json").read_text())


def test_foreign_currency_book_converts_and_charges_the_fx_surcharge_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    shutil.copytree(COMPONENTS_ROOT, tmp_path / "research" / "components")
    seed_catalog_ohlcv(
        tmp_path / "catalog",
        ETF_INSTRUMENT_ID_VALUES,
        periods=300,
        currency="USD",
    )
    # The USD legs convert to the EUR book via this FX pair; without it the run would
    # fail loud (non-base quote currency, no matching exchange: pair).
    seed_catalog_fx(tmp_path / "catalog", _FX_PAIR, periods=300)

    # No-op baseline: all-EUR book, no surcharge - conversion is identity.
    baseline = _run(
        tmp_path,
        capsys,
        _config(catalog_path=tmp_path / "catalog", fx_conversion_cost=0.0),
        "fx-baseline",
    )
    # The foreign path: USD legs + a per-conversion surcharge.
    foreign = _run(
        tmp_path,
        capsys,
        _config(catalog_path=tmp_path / "catalog", fx_conversion_cost=0.001),
        "fx-foreign",
    )

    # It completes end to end, so FX fetch + conversion + surcharge all executed.
    assert [c["role"] for c in foreign["candidates"]] == ["best", "median", "worst"]
    # And it had a real effect: converting the USD legs and charging the surcharge
    # moves the candidate metrics off the all-EUR no-op baseline.
    assert [c["metrics"] for c in foreign["candidates"]] != [
        c["metrics"] for c in baseline["candidates"]
    ]
