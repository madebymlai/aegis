from __future__ import annotations

import importlib
import json
import shutil
import sys
import zipfile
from importlib import metadata as importlib_metadata
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from aegis_runtime import ExecutionBundle as RuntimeExecutionBundle
from aegis_runtime import MarketDataBundle as RuntimeMarketDataBundle

from research.aegis_research import cli
from research.aegis_research.component_registry import (
    ComponentSelection,
    discover_component_registry,
)
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION, load_run_config
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.market_data.currency import assemble_fx_rates, convert_bundle_to_base
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

    payload = _export_bundle(config_path, out_dir="dist")
    wheel_path = Path(payload["wheel"])
    assert wheel_path.name == "aegis_exec_tests_momentum_rotator_01234567-1.0.0-py3-none-any.whl"
    assert payload["install"] == f"uv add {wheel_path}"
    _assert_wheel_metadata(wheel_path)
    _assert_entry_point_metadata(
        wheel_path,
        name="tests.momentum_rotator@bundle-fidelity-run:best",
        value="aegis_exec_tests_momentum_rotator_01234567:bundle",
    )

    prices = _market_data()
    expected = _rd_locked_weights(config_path, prices)
    package_name = _package_name_from_wheel(wheel_path)
    import_path = str(wheel_path.resolve())
    sys.path.insert(0, import_path)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(package_name)
        bundle = module.get_bundle()
        actual = bundle.compute_weights(RuntimeMarketDataBundle(prices.arrays))
    finally:
        sys.path.remove(import_path)
        _remove_imported_package(package_name)
        importlib.invalidate_caches()

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


def test_exported_multi_currency_bundle_converts_native_prices_to_base_weights(
    tmp_path, monkeypatch
) -> None:
    _install_fixture_components(tmp_path)
    usd_symbols = {symbol for symbol in _SYMBOLS if symbol not in {"SPY", "TLT"}}
    currency_by_symbol = {
        symbol: ("USD" if symbol in usd_symbols else "EUR") for symbol in _SYMBOLS
    }
    config_path = _write_locked_config(tmp_path, currency_by_symbol=currency_by_symbol)
    monkeypatch.chdir(tmp_path)
    _seed_candidate_store(config_path)

    payload = _export_bundle(config_path, out_dir="dist")
    wheel_path = Path(payload["wheel"])

    native_prices = _market_data()
    fx_series = _fx_series(native_prices.array("Close").index)
    fx_rates = assemble_fx_rates(fx_series, native_prices.array("Close").index)
    base_prices = convert_bundle_to_base(
        native_prices,
        currency_by_symbol=currency_by_symbol,
        base_currency="EUR",
        fx_rates=fx_rates,
    )
    pd.testing.assert_series_equal(
        base_prices.array("Close")["SPY"], native_prices.array("Close")["SPY"]
    )
    expected = _rd_locked_weights(config_path, base_prices)

    package_name = _package_name_from_wheel(wheel_path)
    import_path = str(wheel_path.resolve())
    sys.path.insert(0, import_path)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(package_name)
        bundle = module.get_bundle()
        actual = bundle.compute_weights(
            RuntimeMarketDataBundle(native_prices.arrays), fx_series=fx_series
        )
    finally:
        sys.path.remove(import_path)
        _remove_imported_package(package_name)
        importlib.invalidate_caches()

    assert bundle.contract.base_currency == "EUR"
    assert bundle.contract.required_fx_currencies == ("USD",)
    assert bundle.contract.currency_by_symbol == currency_by_symbol
    pd.testing.assert_frame_equal(actual, expected)

    with pytest.raises(ValueError, match=r"missing=\['USD'\]"):
        bundle.compute_weights(RuntimeMarketDataBundle(native_prices.arrays), fx_series={})


def test_multiple_exported_bundles_are_discovered_by_entry_points(tmp_path, monkeypatch) -> None:
    _install_fixture_components(tmp_path)
    monkeypatch.chdir(tmp_path)
    out_dir = Path("dist")

    first_config = _write_locked_config(
        tmp_path, path_name="locked_bundle_a.yaml", run_id="bundle-run-a"
    )
    second_config = _write_locked_config(
        tmp_path, path_name="locked_bundle_b.yaml", run_id="bundle-run-b"
    )
    _seed_candidate_store(first_config, run_id="bundle-run-a", candidate_key="aaaa111122223333")
    _seed_candidate_store(second_config, run_id="bundle-run-b", candidate_key="bbbb111122223333")

    _export_bundle(first_config, out_dir=out_dir)
    _export_bundle(second_config, out_dir=out_dir)

    wheels = sorted(out_dir.glob("*.whl"))
    assert [wheel.name for wheel in wheels] == [
        "aegis_exec_tests_momentum_rotator_aaaa1111-1.0.0-py3-none-any.whl",
        "aegis_exec_tests_momentum_rotator_bbbb1111-1.0.0-py3-none-any.whl",
    ]

    names = {
        "tests.momentum_rotator@bundle-run-a:best",
        "tests.momentum_rotator@bundle-run-b:best",
    }
    discovered = _discover_bundle_entry_points(wheels, names)

    assert set(discovered) == names
    assert all(isinstance(bundle, RuntimeExecutionBundle) for bundle in discovered.values())
    assert (
        discovered["tests.momentum_rotator@bundle-run-a:best"].manifest.candidate_key
        == "aaaa111122223333"
    )
    assert (
        discovered["tests.momentum_rotator@bundle-run-b:best"].manifest.candidate_key
        == "bbbb111122223333"
    )


def test_export_rejects_component_without_lookback(tmp_path, monkeypatch) -> None:
    _install_fixture_components(tmp_path)
    # Remove lookback from the strategy component
    strategy_path = tmp_path / "research" / "components" / "strategies" / "tests_momentum_rotator.py"
    strategy_source = strategy_path.read_text()
    # Remove the lookback block (everything between "# %% lookback" and "# %% main compute")
    lookback_start = strategy_source.find("# %% lookback")
    main_start = strategy_source.find("# %% main compute")
    if lookback_start >= 0 and main_start > lookback_start:
        strategy_source_no_lookback = (
            strategy_source[:lookback_start].rstrip("\n")
            + "\n\n"
            + strategy_source[main_start:]
        )
    else:
        strategy_source_no_lookback = strategy_source
    strategy_path.write_text(strategy_source_no_lookback)
    config_path = _write_locked_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    _seed_candidate_store(config_path)

    from research.aegis_research.cli_commands.export import export_locked_bundle

    with pytest.raises(ValueError, match=r"lookback"):
        export_locked_bundle(config_path, out_dir=tmp_path / "dist")


def test_compute_weights_raises_when_window_shorter_than_lookback_bars(
    tmp_path, monkeypatch
) -> None:
    _install_fixture_components(tmp_path)
    config_path = _write_locked_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    _seed_candidate_store(config_path)

    payload = _export_bundle(config_path, out_dir="dist")
    wheel_path = Path(payload["wheel"])
    assert wheel_path.exists()

    # The lookback_bars for momentum_score should be max(h1..h4) = 200
    # with _MOMENTUM_PARAMS h1=15, h2=42, h3=100, h4=200
    package_name = _package_name_from_wheel(wheel_path)
    import_path = str(wheel_path.resolve())
    sys.path.insert(0, import_path)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(package_name)
        bundle = module.get_bundle()
        # lookback_bars should be at least 200 (max of momentum params h4)
        assert bundle.contract.lookback_bars >= 200

        # Supply fewer bars than lookback_bars
        prices = _market_data()
        short_prices = MarketDataBundle(
            {"Close": prices.array("Close").iloc[:50]}
        )
        with pytest.raises(ValueError, match=r"lookback"):
            bundle.compute_weights(RuntimeMarketDataBundle(short_prices.arrays))
    finally:
        sys.path.remove(import_path)
        _remove_imported_package(package_name)
        importlib.invalidate_caches()


def test_compute_weights_raises_when_latest_weight_row_is_non_finite(
    tmp_path, monkeypatch
) -> None:
    _install_fixture_components(tmp_path)
    config_path = _write_locked_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    _seed_candidate_store(config_path)

    payload = _export_bundle(config_path, out_dir="dist")
    wheel_path = Path(payload["wheel"])
    package_name = _package_name_from_wheel(wheel_path)
    import_path = str(wheel_path.resolve())
    sys.path.insert(0, import_path)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module(package_name)
        bundle = module.get_bundle()
        lookback = bundle.contract.lookback_bars

        # Supply exactly lookback_bars — latest row is NaN due to warmup
        prices = _market_data()
        minimal_prices = MarketDataBundle(
            {"Close": prices.array("Close").iloc[:lookback]}
        )
        with pytest.raises(ValueError, match=r"NaN|warmup"):
            bundle.compute_weights(RuntimeMarketDataBundle(minimal_prices.arrays))
    finally:
        sys.path.remove(import_path)
        _remove_imported_package(package_name)
        importlib.invalidate_caches()


def test_export_lengthens_candidate_prefix_when_bundle_name_would_collide(
    tmp_path, monkeypatch
) -> None:
    _install_fixture_components(tmp_path)
    monkeypatch.chdir(tmp_path)
    out_dir = Path("dist")

    first_config = _write_locked_config(
        tmp_path, path_name="locked_bundle_first.yaml", run_id="bundle-collision-a"
    )
    second_config = _write_locked_config(
        tmp_path, path_name="locked_bundle_second.yaml", run_id="bundle-collision-b"
    )
    _seed_candidate_store(
        first_config, run_id="bundle-collision-a", candidate_key="deadbeef00001111"
    )
    _seed_candidate_store(
        second_config, run_id="bundle-collision-b", candidate_key="deadbeef11112222"
    )

    _export_bundle(first_config, out_dir=out_dir)
    _export_bundle(second_config, out_dir=out_dir)

    assert [wheel.name for wheel in sorted(out_dir.glob("*.whl"))] == [
        "aegis_exec_tests_momentum_rotator_deadbeef-1.0.0-py3-none-any.whl",
        "aegis_exec_tests_momentum_rotator_deadbeef1-1.0.0-py3-none-any.whl",
    ]


def test_export_rejects_unlocked_config_with_an_actionable_error(tmp_path, monkeypatch) -> None:
    _install_fixture_components(tmp_path)
    config_path = _write_locked_config(tmp_path, include_lock=False)
    monkeypatch.chdir(tmp_path)
    out_dir = Path("dist")

    stderr = _Stdout()
    exit_code = cli._main(
        ["export", "--config", str(config_path), "--out", str(out_dir)],
        stdout=_Stdout(),
        stderr=stderr,
    )

    assert exit_code != 0
    assert not list(out_dir.glob("*.whl"))  # fail-closed: no wheel written
    message = stderr.text.lower()
    assert "candidate" in message  # explains the params resolve to no single scored Candidate
    assert "lock:" in message  # points at the fix — pin one with `lock: run_id[:role]`


def _export_bundle(config_path: Path, *, out_dir: Path | str) -> dict[str, str]:
    stdout = _Stdout()
    exit_code = cli._main(
        ["export", "--config", str(config_path), "--out", str(out_dir)],
        stdout=stdout,
        stderr=_Stdout(),
    )
    assert exit_code == 0
    payload: dict[str, str] = json.loads(stdout.text)
    return payload


def _assert_wheel_metadata(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        metadata_path = next(name for name in zf.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = zf.read(metadata_path).decode()
        manifest_path = next(
            name for name in zf.namelist() if name.endswith("bundle_manifest.json")
        )
        manifest = json.loads(zf.read(manifest_path))

    assert "Name: aegis-exec-tests-momentum-rotator-01234567" in metadata
    assert "Version: 1.0.0" in metadata
    assert "Requires-Dist: aegis-runtime" in metadata
    assert manifest["manifest"]["run_id"] == _RUN_ID
    assert manifest["manifest"]["component_source_hashes"]


def _assert_entry_point_metadata(wheel_path: Path, *, name: str, value: str) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        entry_points_path = next(
            name for name in zf.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = zf.read(entry_points_path).decode()

    assert "[aegis.execution_bundles]" in entry_points
    assert f"{name} = {value}" in entry_points


def _discover_bundle_entry_points(
    wheels: list[Path], names: set[str]
) -> dict[str, RuntimeExecutionBundle]:
    entries = [str(wheel) for wheel in wheels]
    sys.path[:0] = entries
    importlib.invalidate_caches()
    packages = [_package_name_from_wheel(wheel) for wheel in wheels]
    try:
        entry_points = importlib_metadata.entry_points(group="aegis.execution_bundles")
        return {ep.name: ep.load() for ep in entry_points if ep.name in names}
    finally:
        del sys.path[: len(entries)]
        for package in packages:
            _remove_imported_package(package)
        importlib.invalidate_caches()


def _remove_imported_package(package: str) -> None:
    for module_name in list(sys.modules):
        if module_name == package or module_name.startswith(f"{package}."):
            sys.modules.pop(module_name, None)


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


def _seed_candidate_store(
    config_path: Path, *, run_id: str = _RUN_ID, candidate_key: str = _CANDIDATE_KEY
) -> None:
    registry = discover_component_registry()
    config = load_run_config(config_path, component_registry=registry).config
    provenance = {"source": _source_provenance(registry)}
    row = {
        "role": "best",
        "rank": 1,
        "candidate_key": candidate_key,
        "params": {FIXED_CANDIDATE_PARAM: 0},
        "identity": {"test": "bundle-fidelity"},
        "score": 1.0,
        "selection_metrics": {},
        "held_out_metrics": {},
        "metrics": {},
    }
    rows = [dict(row, role=role, rank=i) for i, role in enumerate(("best", "median", "worst"), 1)]
    with CandidateStore(candidate_store_path(config)) as store:
        store.insert_completed_run(run_id=run_id, candidate_rows=rows, provenance=provenance)


def _source_provenance(registry) -> dict[str, object]:
    return {
        "strategy": _runtime(
            registry, "strategies", "tests.momentum_rotator", "strategy", _STRATEGY_PARAMS
        ),
        "indicators": [
            _runtime(
                registry,
                "indicators",
                "tests.momentum_score",
                "tests.momentum_score",
                _MOMENTUM_PARAMS,
            ),
            _runtime(
                registry, "indicators", "tests.realized_vol", "tests.realized_vol", _VOL_PARAMS
            ),
        ],
    }


def _runtime(
    registry, family: str, component_id: str, slot: str, params: dict[str, object]
) -> dict[str, object]:
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


def _fx_series(index: pd.Index) -> dict[str, pd.Series]:
    base = np.arange(len(index), dtype=float)
    # EURUSD quote: native USD per 1 EUR. A rising series makes USD-quoted
    # symbols move differently after conversion while EUR symbols pass through.
    return {"USD": pd.Series(1.10 + base * 0.0005, index=index, name="USD")}


def _install_fixture_components(tmp_path: Path) -> None:
    for family in ("indicators", "strategies"):
        target = tmp_path / "research" / "components" / family
        target.mkdir(parents=True)
        for source in sorted((_FIXTURES / "components" / family).glob("*.py")):
            shutil.copy(source, target / source.name)


def _write_locked_config(
    tmp_path: Path,
    *,
    path_name: str = "locked_bundle.yaml",
    run_id: str = _RUN_ID,
    currency_by_symbol: dict[str, str] | None = None,
    include_lock: bool = True,
) -> Path:
    path = tmp_path / path_name
    currency_by_symbol = currency_by_symbol or dict.fromkeys(_SYMBOLS, "EUR")
    config: dict[str, object] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "locked_bundle",
        "output_dir": "runs",
        "lock": f"{run_id}:best",
        "data": {
            "source": "synthetic",
            "symbols": [
                {"ticker": symbol, "ccy": currency_by_symbol[symbol]} for symbol in _SYMBOLS
            ],
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
    }
    if not include_lock:
        del config["lock"]
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _package_name_from_wheel(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        packages = sorted(
            name.split("/")[0] for name in zf.namelist() if name.endswith("__init__.py")
        )
    return packages[0]


class _Stdout:
    def __init__(self) -> None:
        self.text = ""

    def write(self, value: str) -> None:
        self.text += value
