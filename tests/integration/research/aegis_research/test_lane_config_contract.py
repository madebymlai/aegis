from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    load_lane_config,
    resolve_lane_config,
)


def test_valid_lane_configs_resolve_with_lane_identity(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    play = resolve_lane_config(_play_config(), component_registry=registry)
    run = resolve_lane_config(_run_config(), component_registry=registry)
    train = resolve_lane_config(_train_config(), component_registry=registry)

    assert play.lane == "play"
    assert play.config.play.ranking.metric == "total_return_pct"
    assert run.lane == "run"
    assert run.config.strategy.id == "demo.strategy"
    assert train.lane == "train"
    assert train.config.label.id == "demo.label"
    assert train.config.model.plugin_id == "tests.sklearn_logistic"
    assert play.manifest()["lane"] == "play"


def test_load_lane_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "lane.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "lane: play",
                "name: duplicate_lane",
                "play: {}",
                "play: {}",
                "portfolio:",
                "  entry_budget: 1.0",
            ]
        )
    )

    with pytest.raises(ConfigValidationError, match="duplicate mapping key"):
        load_lane_config(path)


@pytest.mark.parametrize(
    ("lane", "mutations", "expected_path"),
    [
        ("play", {"play": {"notebook_path": "../unsafe.ipynb"}}, "play.notebook_path"),
        ("play", {"play": {"formula": "close > close.rolling(5).mean()"}}, "play.formula"),
        ("run", {"strategy": {"source": "component", "id": "demo.strategy", "import": "x.y"}}, "strategy.import"),
        ("run", {"strategy": {"source": "component", "id": "demo.strategy", "path": "strategy.py"}}, "strategy.path"),
        ("train", {"label": {"source": "component", "id": "demo.label", "artifact_path": "runs/play/last-run"}}, "label.artifact_path"),
        ("train", {"label": {"source": "component", "id": "demo.label", "python": "lambda x: x"}}, "label.python"),
    ],
)
def test_lane_configs_reject_inline_code_and_arbitrary_paths(
    tmp_path: Path,
    lane: str,
    mutations: dict[str, object],
    expected_path: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = {"play": _play_config(), "run": _run_config(), "train": _train_config()}[lane]
    raw = _merge(raw, mutations)

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry)

    assert expected_path in str(error.value)
    assert "not allowed" in str(error.value)


def test_strategy_run_rejects_model_training_config_with_train_guidance(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "model": {"plugin_id": "tests.sklearn_logistic"},
            "labels": {"source": "component", "id": "demo.label"},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry)

    assert "model" in str(error.value)
    assert "aerd train" in str(error.value)


def test_train_rejects_strategy_sweep_config_with_missing_training_contract(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "train",
        "name": "missing_training_contract",
        "strategy": {"source": "component", "id": "demo.strategy"},
        "portfolio": {"entry_budget": 1.0},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry)

    assert "model.plugin_id" in str(error.value)
    assert "training contract" in str(error.value)


@pytest.mark.parametrize(
    ("ranking", "expected"),
    [
        ({"metric": "not_a_metric", "direction": "desc"}, "ranking.metric"),
        ({"metric": "total_return_pct", "direction": "sideways"}, "ranking.direction"),
        ({"metric": "total_return_pct"}, "ranking.direction"),
    ],
)
def test_lane_ranking_metric_and_direction_validation(
    tmp_path: Path,
    ranking: dict[str, str],
    expected: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _play_config()
    raw["play"]["ranking"] = ranking  # type: ignore[index]

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry)

    assert expected in str(error.value)


def _play_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "play",
        "name": "play_demo",
        "data": {"source": "synthetic", "rows": 50},
        "portfolio": {"entry_budget": 1.0},
        "play": {
            "stages": ["indicators"],
            "indicator_refs": [{"source": "playbook", "id": "ma_explore"}],
            "ranking": {"metric": "total_return_pct", "direction": "desc"},
        },
    }


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "run",
        "name": "strategy_demo",
        "data": {"source": "synthetic", "rows": 50},
        "portfolio": {"entry_budget": 1.0},
        "strategy": {"source": "component", "id": "demo.strategy"},
        "indicator_refs": [{"source": "component", "id": "demo.indicator"}],
        "ranking": {"metric": "sharpe_ratio", "direction": "desc"},
    }


def _train_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "lane": "train",
        "name": "train_demo",
        "data": {"source": "synthetic", "rows": 50},
        "portfolio": {"entry_budget": 1.0},
        "label": {"source": "component", "id": "demo.label"},
        "indicators": {
            "specs": [
                {
                    "id": "ma",
                    "params": {"window": [5], "wtype": "simple"},
                    "outputs": ["ma"],
                    "model_features": [{"output": "ma", "transform": "distance_to_close"}],
                }
            ]
        },
        "model": {"plugin_id": "tests.sklearn_logistic"},
    }


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    _write_component(root / "labels" / "label.py", "labels", "demo.label")
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.indicator")
    _write_component(root / "strategies" / "strategy.py", "strategies", "demo.strategy")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_component(path: Path, family: str, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_for(family, component_id)
    path.write_text(
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run():\n"
        "    pass\n"
    )


def _manifest_for(family: str, component_id: str) -> dict[str, object]:
    base = {"family": family, "id": component_id, "version": "1.0.0"}
    if family == "labels":
        return {
            **base,
            "target_role": "supervised_target",
            "target_kind": "binary_classification",
            "output_names": ["labels"],
            "split_safety": {"purging_required": True},
        }
    if family == "indicators":
        return {
            **base,
            "input_names": ["close"],
            "param_names": ["window"],
            "output_names": ["value"],
            "default_outputs": ["value"],
            "default_model_features": [{"output": "value", "transform": "identity"}],
            "supported_transforms": ["identity"],
        }
    if family == "strategies":
        return {
            **base,
            "signal_outputs": ["entries", "exits"],
            "owns_portfolio": False,
        }
    raise AssertionError(family)


def _merge(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged
