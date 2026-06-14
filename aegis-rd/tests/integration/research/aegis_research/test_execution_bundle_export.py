from __future__ import annotations

import importlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from aegis_runtime import MarketDataBundle as RuntimeMarketDataBundle
from research.aegis_research import cli
from research.aegis_research.component_registry import (
    ComponentSelection,
    discover_component_registry,
)
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION, load_run_config
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.candidate_publishing import candidate_store_path
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.component_source import (
    build_component_optimization_source,
)
from research.aegis_research.optimization.lock_run import resolve_lock_run
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from research.aegis_research.optimization.precompute import candidate_keys

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
_RUN_ID = "bundle-fidelity-run"
_CANDIDATE_KEY = "0123456789abcdef0123456789abcdef"
_SYMBOLS = ("SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU")
_MOMENTUM_PARAMS = {
    "h1": 15,
    "h2": 42,
    "h3": 100,
    "h4": 200,
    "w1": 8.0,
    "w2": 4.0,
    "w3": 3.0,
    "w4": 2.0,
}
_VOL_PARAMS = {"window": 20}
_STRATEGY_PARAMS = {"top_n": 3, "top_k_defensive": 1, "tau": 0.08}


def test_exported_base_currency_bundle_matches_locked_rd_weights(tmp_path, monkeypatch) -> None:
    _install_fixture_components(tmp_path)
    config_path = _write_locked_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    _seed_candidate_store(config_path)

    stdout = _Stdout()
    assert cli._main(["export", "--config", str(config_path), "--out", "dist"], stdout=stdout, stderr=_Stdout()) == 0
    payload = json.loads(stdout.text)
    wheel_path = Path(payload["wheel"])
    assert wheel_path.name == "aegis_exec_tests_momentum_rotator_01234567-1.0.0-py3-none-any.whl"
    assert payload["install"] == f"uv add {wheel_path}"
    _assert_wheel_metadata(wheel_path)

    prices = _market_data()
    expected = _rd_locked_weights(config_path, prices)
    package_name = _package_name_from_wheel(wheel_path)
    sys.path.insert(0, str(wheel_path))
    try:
        module = importlib.import_module(package_name)
        bundle = module.get_bundle()
        actual = bundle.compute_weights(RuntimeMarketDataBundle(prices.arrays))
    finally:
        sys.path.remove(str(wheel_path))
        sys.modules.pop(package_name, None)

    assert bundle.contract.symbols == _SYMBOLS
    assert bundle.contract.required_arrays == ("Close",)
    assert bundle.manifest.run_id == _RUN_ID
    assert bundle.manifest.role == "best"
    assert bundle.manifest.candidate_key == _CANDIDATE_KEY
    pd.testing.assert_frame_equal(actual, expected)

    with pytest.raises(ValueError, match="symbols"):
        bundle.compute_weights(
            RuntimeMarketDataBundle({"Close": prices.array("Close").rename(columns={"SPY": "BAD"})})
        )


def _assert_wheel_metadata(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        metadata_path = next(name for name in zf.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = zf.read(metadata_path).decode()
        manifest_path = next(name for name in zf.namelist() if name.endswith("bundle_manifest.json"))
        manifest = json.loads(zf.read(manifest_path))

    assert "Name: aegis-exec-tests-momentum-rotator-01234567" in metadata
    assert "Version: 1.0.0" in metadata
    assert "Requires-Dist: aegis-runtime" in metadata
    assert manifest["manifest"]["run_id"] == _RUN_ID
    assert manifest["manifest"]["component_source_hashes"]


def _rd_locked_weights(config_path: Path, prices: MarketDataBundle) -> pd.DataFrame:
    registry = discover_component_registry()
    resolved = load_run_config(config_path, component_registry=registry)
    config = resolved.config
    with CandidateStore(candidate_store_path(config)) as store:
        lock_run = resolve_lock_run(config.lock, store=store)  # type: ignore[arg-type]
    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=prices,
        resolved_component_params=lock_run.component_params,
        force_locked=True,
    )
    param_lists = {FIXED_CANDIDATE_PARAM: [0]}
    precomputed = source.precompute(prices.array("Close"), 1, **param_lists)
    indicator_window = precomputed.window(slice(None), candidate_keys(param_lists))
    locked = source.simulate(prices.array("Close"), indicator_window, 1, **param_lists)
    return locked.droplevel([name for name in locked.columns.names if name != "symbol"], axis=1)


def _seed_candidate_store(config_path: Path) -> None:
    registry = discover_component_registry()
    config = load_run_config(config_path, component_registry=registry).config
    provenance = {"source": _source_provenance(registry)}
    row = {
        "role": "best",
        "rank": 1,
        "candidate_key": _CANDIDATE_KEY,
        "params": {FIXED_CANDIDATE_PARAM: 0},
        "identity": {"test": "bundle-fidelity"},
        "score": 1.0,
        "selection_metrics": {},
        "held_out_metrics": {},
        "metrics": {},
    }
    rows = [dict(row, role=role, rank=i) for i, role in enumerate(("best", "median", "worst"), 1)]
    with CandidateStore(candidate_store_path(config)) as store:
        store.insert_completed_run(run_id=_RUN_ID, candidate_rows=rows, provenance=provenance)


def _source_provenance(registry) -> dict[str, object]:
    return {
        "strategy": _runtime(registry, "strategies", "tests.momentum_rotator", "strategy", _STRATEGY_PARAMS),
        "indicators": [
            _runtime(registry, "indicators", "tests.momentum_score", "tests.momentum_score", _MOMENTUM_PARAMS),
            _runtime(registry, "indicators", "tests.realized_vol", "tests.realized_vol", _VOL_PARAMS),
        ],
    }


def _runtime(registry, family: str, component_id: str, slot: str, params: dict[str, object]) -> dict[str, object]:
    definition = registry.get(ComponentSelection(family, component_id))
    return {
        "family": family,
        "slot": slot,
        "id": component_id,
        "version": definition.manifest.version,
        **definition.identity.public(),
        "fixed_params": params,
        "param_keys": {},
    }


def _market_data() -> MarketDataBundle:
    index = pd.date_range("2020-01-01", periods=320, freq="D")
    base = np.arange(len(index), dtype=float).reshape(-1, 1)
    offsets = np.arange(len(_SYMBOLS), dtype=float).reshape(1, -1)
    trend = 100.0 + base * (0.05 + offsets / 2000.0)
    seasonal = np.sin(base / 9.0 + offsets) * 0.8
    close = pd.DataFrame(trend + seasonal, index=index, columns=_SYMBOLS)
    return MarketDataBundle({"Close": close})


def _install_fixture_components(tmp_path: Path) -> None:
    for family in ("indicators", "strategies"):
        target = tmp_path / "research" / "components" / family
        target.mkdir(parents=True)
        for source in sorted((_FIXTURES / "components" / family).glob("*.py")):
            shutil.copy(source, target / source.name)


def _write_locked_config(tmp_path: Path) -> Path:
    path = tmp_path / "locked_bundle.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "locked_bundle",
                "output_dir": "runs",
                "lock": f"{_RUN_ID}:best",
                "data": {
                    "source": "synthetic",
                    "symbols": [{"ticker": symbol, "ccy": "EUR"} for symbol in _SYMBOLS],
                    "rows": 320,
                    "seed": 7,
                    "timeframe": "1D",
                    "arrays": ["Close"],
                },
                "portfolio": {"gross_cap": 1.0, "direction": "longonly", "base_currency": "EUR"},
                "strategy": {"id": "tests.momentum_rotator"},
                "indicators": [
                    {"id": "tests.momentum_score"},
                    {"id": "tests.realized_vol"},
                ],
                "ranking": {"metric": "sharpe_ratio"},
                "optimization": {
                    "search": "grid",
                    "split": {
                        "method": "from_rolling",
                        "params": {"length": 252, "offset": 0, "split": 0.5},
                    },
                },
            },
            sort_keys=False,
        )
    )
    return path


def _package_name_from_wheel(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        packages = sorted(name.split("/")[0] for name in zf.namelist() if name.endswith("__init__.py"))
    return packages[0]


class _Stdout:
    def __init__(self) -> None:
        self.text = ""

    def write(self, value: str) -> None:
        self.text += value
