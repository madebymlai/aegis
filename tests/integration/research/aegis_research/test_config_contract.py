from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from research.aegis_research import config as config_module
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    OHLCV_ARRAYS,
    ConfigValidationError,
    DataConfig,
    load_run_config,
    resolve_run_config,
    resolve_secret_refs,
)
from tests.support.research.aegis_research.component_fixtures import write_indicator_component


def test_public_config_exports_only_run_config_contract() -> None:
    removed = {
        "ExperimentConfig",
        "ResolvedExperimentConfig",
        "load_experiment_config",
        "resolve_experiment_config",
        "LaneConfig",
        "ResolvedLaneConfig",
        "StrategyRunLaneConfig",
        "TrainLaneConfig",
        "TrainModelConfig",
        "LabelerConfig",
        "LANES",
    }

    for name in removed:
        assert not hasattr(config_module, name)
    assert hasattr(config_module, "RunConfig")
    assert hasattr(config_module, "OptimizationConfig")
    assert hasattr(config_module, "ResolvedRunConfig")
    assert hasattr(config_module, "load_run_config")
    assert hasattr(config_module, "resolve_run_config")


def test_resolved_run_config_attaches_default_metric_registry(tmp_path: Path) -> None:
    resolved = resolve_run_config(
        _run_config(),
        component_registry=_component_registry(tmp_path),
    )

    resolved_without_metric_registry = replace(resolved, metric_registry=None)

    reresolved = resolve_run_config(resolved_without_metric_registry)

    assert reresolved.metric_registry is not None


def test_run_config_rejects_removed_labeler_field(tmp_path: Path) -> None:
    raw = _run_config()
    raw["labeler"] = {"id": "demo.fixlb"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path, include_strategy=True),
        )

    assert "labeler" in str(error.value)
    assert "training and lane fields are not supported" in str(error.value)


def test_data_arrays_single_ohlcv_resolves_effective_set(tmp_path: Path) -> None:
    resolved = resolve_run_config(
        _run_config(),
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.arrays == ["OHLCV"]
    assert resolved.config.data.effective_arrays == OHLCV_ARRAYS


def test_data_arrays_mixed_shortcut_dedupes_deterministically(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["FundingRate", "OHLCV", "Close", "FundingRate"],
    }

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.effective_arrays == (
        "FundingRate",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    )


def test_data_arrays_accept_source_specific_vbt_feature_names(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["Close", "Stock Splits", "close"],
    }

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.effective_arrays == ("Close", "Stock Splits", "close")


def test_run_config_requires_explicit_data_arrays(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {"source": "synthetic", "symbols": ["SYN"], "rows": 120}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.arrays" in str(error.value)
    assert "required" in str(error.value)


def test_run_config_rejects_removed_feature_map(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["OHLCV"],
        "feature_map": {"close": "price"},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.feature_map" in str(error.value)
    assert "unknown field" in str(error.value)


@pytest.mark.parametrize("arrays", ["OHLCV", ["Close "], [""], [1], []])
def test_run_config_rejects_invalid_data_arrays(tmp_path: Path, arrays: object) -> None:
    raw = _run_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": arrays,
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.arrays" in str(error.value)


def test_legacy_train_shape_is_not_a_run_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "legacy_shape",
                "labels": {"generator": {"kind": "fixlb"}},
                "model": {"plugin_id": "aegis.sklearn_logistic"},
                "portfolio": {"entry_budget": 1.0},
            },
            component_registry=_component_registry(tmp_path),
        )

    assert "labels" in str(error.value)
    assert "model" in str(error.value)
    assert "single run config contract" in str(error.value)


def test_load_run_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "name: duplicate_key_test",
                "data:",
                "  source: synthetic",
                "data:",
                "  source: synthetic",
                "portfolio:",
                "  entry_budget: 1.0",
                "strategy: {}",
                "indicators: []",
                "",
            ]
        )
    )

    with pytest.raises(ConfigValidationError) as error:
        load_run_config(path, component_registry=_component_registry(tmp_path))

    assert "data" in str(error.value)
    assert "duplicate mapping key" in str(error.value)


def test_env_secret_refs_are_redacted_and_resolved_at_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "super-secret-token")
    config = DataConfig(
        source="binance",
        symbols=["BTCUSDT"],
        start="2020-01-01",
        end="2020-02-01",
        timeframe="1D",
        provider_kwargs={"api_key": {"env": "BINANCE_API_KEY"}},
    )

    resolved_kwargs, secrets = resolve_secret_refs(config.provider_kwargs)

    assert resolved_kwargs == {"api_key": "super-secret-token"}
    assert secrets == ["super-secret-token"]


def test_run_accepts_candidate_grid_policy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["candidate_grid"] = {"max_candidates": 100, "max_estimated_cells": 10_000, "batch_size": 25}

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.candidate_grid.max_candidates == 100
    assert resolved.config.candidate_grid.max_estimated_cells == 10_000
    assert resolved.config.candidate_grid.batch_size == 25


def test_run_accepts_native_grid_optimization_with_nested_split(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _native_optimization(search="grid")

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "grid"
    assert resolved.config.optimization.random_subset is None
    assert resolved.config.optimization.seed is None
    assert resolved.config.optimization.execute == {}
    assert resolved.config.optimization.evidence.return_grid == "first"
    assert resolved.config.optimization.split.method == "from_rolling"
    assert resolved.config.optimization.split.params["set_labels"] == ["selection", "held_out"]


def test_run_accepts_native_random_optimization_policy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _native_optimization(
        search="random",
        random_subset=5,
        seed=42,
        execute={"engine": "threadpool", "chunk_len": "auto"},
        evidence={"return_grid": "all"},
    )

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "random"
    assert resolved.config.optimization.random_subset == 5
    assert resolved.config.optimization.seed == 42
    assert resolved.config.optimization.execute == {"engine": "threadpool", "chunk_len": "auto"}
    assert resolved.config.optimization.evidence.return_grid == "all"


@pytest.mark.parametrize(
    ("optimization", "expected_path", "expected_message"),
    [
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                        "set_labels": ["selection", "held_out"],
                    },
                },
                "engine": "custom",
            },
            "optimization.engine",
            "unknown field",
        ),
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                        "set_labels": ["selection", "held_out"],
                    },
                },
                "mode": "native",
            },
            "optimization.mode",
            "unknown field",
        ),
        (
            {
                "search": "random",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                        "set_labels": ["selection", "held_out"],
                    },
                },
            },
            "optimization.random_subset",
            "is required",
        ),
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                        "set_labels": ["selection", "held_out"],
                    },
                },
                "random_subset": 5,
            },
            "optimization.random_subset",
            "only valid when optimization.search is 'random'",
        ),
        (
            {"search": "grid"},
            "optimization.split",
            "is required",
        ),
    ],
)
def test_run_rejects_invalid_native_optimization_policy(
    tmp_path: Path,
    optimization: dict[str, object],
    expected_path: str,
    expected_message: str,
) -> None:
    raw = _run_config()
    raw["optimization"] = optimization

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert expected_path in str(error.value)
    assert expected_message in str(error.value)


def test_run_rejects_top_level_split_as_native_optimization_split(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = {"search": "grid"}
    raw["split"] = _optimization_split()

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "optimization.split" in str(error.value)
    assert "move the split policy under optimization.split" in str(error.value)


def test_run_rejects_candidate_grid_on_native_optimization_config(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _native_optimization(search="grid")
    raw["candidate_grid"] = {"max_candidates": 100, "max_estimated_cells": 10_000}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "candidate_grid" in str(error.value)
    assert "native optimization uses optimization.search" in str(error.value)


def test_run_rejects_native_optimization_component_param_space_boundary(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _native_optimization(search="grid")
    raw["strategy"] = {"source": "component", "id": "demo.strategy"}
    raw["indicators"] = [{"source": "component", "ids": ["demo.returns"]}]

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path, include_strategy=True),
        )

    assert "strategy.source" in str(error.value)
    assert "component param spaces are #32" in str(error.value)


def test_run_rejects_playbook_indicators_with_component_strategy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["strategy"] = {"source": "component", "id": "demo.strategy"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path, include_strategy=True),
        )

    assert "indicators[0].source" in str(error.value)
    assert "cannot enter the component runner" in str(error.value)


@pytest.mark.parametrize(
    ("policy", "expected_path"),
    [
        ({"max_candidates": 0}, "candidate_grid.max_candidates"),
        ({"batch_size": 0}, "candidate_grid.batch_size"),
        ({"batch_size": "100"}, "candidate_grid.batch_size"),
    ],
)
def test_run_rejects_invalid_candidate_grid_policy(
    tmp_path: Path,
    policy: dict[str, object],
    expected_path: str,
) -> None:
    raw = _run_config()
    raw["candidate_grid"] = policy

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert expected_path in str(error.value)


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "canonical_run",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "strategy": {"source": "playbook", "id": "ma_cross"},
        "indicators": [{"source": "playbook", "ids": ["ma_explore"]}],
        "ranking": {"metric": "total_return", "direction": "desc"},
    }


def _native_optimization(search: str, **overrides: object) -> dict[str, object]:
    return {"search": search, "split": _optimization_split(), **overrides}


def _optimization_split() -> dict[str, object]:
    return {
        "method": "from_rolling",
        "params": {"length": 20, "split": 0.5, "set_labels": ["selection", "held_out"]},
        "max_splits": 10,
    }


def _component_registry(tmp_path: Path, *, include_strategy: bool = False):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    if include_strategy:
        _write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture component used by config tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'signal_outputs': ['entries', 'exits']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        "    \"\"\"Return fixed strategy signals for config validation tests.\"\"\"\n"
        "    raise RuntimeError('not executed during config tests')\n"
    )
