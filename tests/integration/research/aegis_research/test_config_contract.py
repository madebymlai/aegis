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
    load_lane_config,
    resolve_lane_config,
    resolve_secret_refs,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_label_component,
)
from tests.support.research.aegis_research.model_plugin_fixtures import make_model_registry


def test_public_config_exports_only_canonical_lane_config() -> None:
    assert not hasattr(config_module, "ExperimentConfig")
    assert not hasattr(config_module, "ResolvedExperimentConfig")
    assert not hasattr(config_module, "load_experiment_config")
    assert not hasattr(config_module, "resolve_experiment_config")


def test_train_lane_config_resolves_model_registry_contract(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    resolved = resolve_lane_config(
        _train_config(),
        component_registry=registry,
        model_registry=make_model_registry(),
        expected_lane="train",
    )

    assert resolved.lane == "train"
    assert resolved.config.labeler.id == "demo.fixlb"
    assert resolved.config.model.plugin_id == "aegis.sklearn_logistic"
    assert resolved.model_registry is not None


def test_resolved_train_lane_config_attaches_default_metric_registry(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    resolved = resolve_lane_config(
        _train_config(),
        component_registry=registry,
        model_registry=make_model_registry(),
        expected_lane="train",
    )

    resolved_without_metric_registry = replace(resolved, metric_registry=None)

    reresolved = resolve_lane_config(resolved_without_metric_registry, expected_lane="train")

    assert reresolved.metric_registry is not None


def test_train_lane_rejects_nested_legacy_label_selection(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw.pop("labeler")
    raw["train"] = {
        **raw["train"],  # type: ignore[dict-item]
        "label": {"source": "component", "id": "demo.fixlb"},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "train.label" in str(error.value)
    assert "top-level labeler" in str(error.value)


@pytest.mark.parametrize(
    "extra_key",
    [
        "source",
        "params",
        "path",
        "notebook_path",
        "artifact_path",
        "python",
        "code",
        "formula",
        "sweep",
        "axis",
    ],
)
def test_train_lane_rejects_labeler_extra_keys(tmp_path: Path, extra_key: str) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["labeler"] = {"id": "demo.fixlb", extra_key: "not-allowed"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert f"labeler.{extra_key}" in str(error.value)


def test_train_lane_rejects_missing_labeler(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw.pop("labeler")

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "labeler" in str(error.value)
    assert "required" in str(error.value)


def test_train_lane_rejects_scalar_labeler(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["labeler"] = "demo.fixlb"

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "labeler" in str(error.value)
    assert "mapping" in str(error.value)


def test_train_lane_rejects_unknown_labeler_id(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["labeler"] = {"id": "unknown.fixlb"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "labeler.id" in str(error.value)
    assert "unknown label component id" in str(error.value)


@pytest.mark.parametrize("labeler_id", [None, "", "all", "bad/id"])
def test_train_lane_rejects_invalid_labeler_id(tmp_path: Path, labeler_id: object) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["labeler"] = {"id": labeler_id}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "labeler.id" in str(error.value)


@pytest.mark.parametrize("expected_lane", ["run", "train"])
def test_lane_config_rejects_strategy_and_labeler_together(
    tmp_path: Path, expected_lane: str
) -> None:
    registry = _component_registry(tmp_path, include_strategy=True)
    raw = _run_config()
    raw["labeler"] = {"id": "demo.fixlb"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane=expected_lane,
        )

    assert "labeler" in str(error.value)
    assert "strategy" in str(error.value)
    assert "mutually exclusive" in str(error.value)


def test_data_arrays_single_ohlcv_resolves_effective_set(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    resolved = resolve_lane_config(
        _train_config(),
        component_registry=registry,
        model_registry=make_model_registry(),
        expected_lane="train",
    )

    assert resolved.config.data.arrays == ["OHLCV"]
    assert resolved.config.data.effective_arrays == OHLCV_ARRAYS


def test_data_arrays_mixed_shortcut_dedupes_deterministically(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["FundingRate", "OHLCV", "Close", "FundingRate"],
    }

    resolved = resolve_lane_config(
        raw,
        component_registry=registry,
        model_registry=make_model_registry(),
        expected_lane="train",
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
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["Close", "Stock Splits", "close"],
    }

    resolved = resolve_lane_config(
        raw,
        component_registry=registry,
        model_registry=make_model_registry(),
        expected_lane="train",
    )

    assert resolved.config.data.effective_arrays == ("Close", "Stock Splits", "close")


def test_lane_config_requires_explicit_data_arrays(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["data"] = {"source": "synthetic", "symbols": ["SYN"], "rows": 120}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "data.arrays" in str(error.value)
    assert "required" in str(error.value)


def test_lane_config_rejects_removed_feature_map(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": ["OHLCV"],
        "feature_map": {"close": "price"},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "data.feature_map" in str(error.value)
    assert "unknown field" in str(error.value)


@pytest.mark.parametrize("arrays", ["OHLCV", ["Close "], [""], [1], []])
def test_lane_config_rejects_invalid_data_arrays(tmp_path: Path, arrays: object) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "rows": 120,
        "arrays": arrays,
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "data.arrays" in str(error.value)


def test_train_lane_config_rejects_unknown_model_with_registry(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["train"]["model"]["id"] = "unknown.model"  # type: ignore[index]

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=registry,
            model_registry=make_model_registry(),
            expected_lane="train",
        )

    assert "train.model.id" in str(error.value)
    assert "unknown registered model plugin id" in str(error.value)


def test_legacy_experiment_shape_is_not_a_canonical_config(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "legacy_shape",
                "labels": {"generator": {"kind": "fixlb"}},
                "model": {"plugin_id": "aegis.sklearn_logistic"},
                "portfolio": {"entry_budget": 1.0},
            },
            component_registry=registry,
            expected_lane="train",
        )

    assert "labels" in str(error.value)
    assert "model" in str(error.value)
    assert "train" in str(error.value)


def test_load_lane_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "train.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "lane: train",
                "name: duplicate_key_test",
                "data:",
                "  source: synthetic",
                "data:",
                "  source: synthetic",
                "portfolio:",
                "  entry_budget: 1.0",
                "train: {}",
                "indicators: []",
                "",
            ]
        )
    )

    with pytest.raises(ConfigValidationError) as error:
        load_lane_config(
            path, component_registry=_component_registry(tmp_path), expected_lane="train"
        )

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


def test_run_lane_accepts_candidate_grid_policy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["candidate_grid"] = {"max_candidates": 100, "max_estimated_cells": 10_000, "batch_size": 25}

    resolved = resolve_lane_config(
        raw,
        component_registry=_component_registry(tmp_path),
        expected_lane="run",
    )

    assert resolved.config.candidate_grid.max_candidates == 100
    assert resolved.config.candidate_grid.max_estimated_cells == 10_000
    assert resolved.config.candidate_grid.batch_size == 25


def test_run_lane_rejects_playbook_indicators_with_component_strategy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["strategy"] = {"source": "component", "id": "demo.strategy"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=_component_registry(tmp_path, include_strategy=True),
            expected_lane="run",
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
def test_run_lane_rejects_invalid_candidate_grid_policy(
    tmp_path: Path,
    policy: dict[str, object],
    expected_path: str,
) -> None:
    raw = _run_config()
    raw["candidate_grid"] = policy

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(
            raw,
            component_registry=_component_registry(tmp_path),
            expected_lane="run",
        )

    assert expected_path in str(error.value)


def _train_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "train",
        "name": "canonical_train",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "labeler": {"id": "demo.fixlb"},
        "indicators": [{"source": "component", "ids": ["demo.returns"]}],
        "train": {
            "model": {
                "source": "plugin",
                "id": "aegis.sklearn_logistic",
                "params": {"max_iter": 1000, "random_state": 42},
            },
        },
    }


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "run",
        "name": "canonical_run",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "strategy": {"source": "playbook", "id": "ma_cross"},
        "indicators": [{"source": "playbook", "ids": ["ma_explore"]}],
        "ranking": {"metric": "total_return", "direction": "desc"},
    }


def _component_registry(tmp_path: Path, *, include_strategy: bool = False):
    root = tmp_path / "research" / "components"
    write_label_component(
        root / "labels" / "fixlb.py",
        body="def run(data):\n    raise RuntimeError('not executed during config tests')\n",
    )
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
