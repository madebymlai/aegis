from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research.aegis_research import config as config_module
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    DataConfig,
    load_lane_config,
    resolve_lane_config,
    resolve_secret_refs,
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
    assert resolved.config.model.plugin_id == "aegis.sklearn_logistic"
    assert resolved.model_registry is not None


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
        load_lane_config(path, component_registry=_component_registry(tmp_path), expected_lane="train")

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


def _train_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "train",
        "name": "canonical_train",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120},
        "portfolio": {"entry_budget": 1.0},
        "indicators": [{"source": "component", "ids": ["demo.returns"]}],
        "train": {
            "label": {"source": "component", "id": "demo.fixlb"},
            "model": {
                "source": "plugin",
                "id": "aegis.sklearn_logistic",
                "params": {"max_iter": 1000, "random_state": 42},
            },
        },
    }


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    _write_label_component(root / "labels" / "fixlb.py")
    _write_indicator_component(root / "indicators" / "returns.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_label_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "COMPONENT_MANIFEST = {"
        "'family': 'labels', 'id': 'demo.fixlb', 'version': '1.0.0', "
        "'target_role': 'supervised_target', 'target_kind': 'binary_classification', "
        "'output_names': ['labels']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run(close, *, params):\n"
        "    raise RuntimeError('not executed during config tests')\n"
    )


def _write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.returns', 'version': '1.0.0', "
        "'input_names': ['close'], 'param_names': [], 'output_names': ['returns'], "
        "'default_outputs': ['returns'], "
        "'default_model_features': [{'output': 'returns', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run(close, *, params):\n"
        "    return close.pct_change().fillna(0.0)\n"
    )
