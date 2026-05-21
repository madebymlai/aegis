from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    PortfolioConfig,
    RankingConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    StrategyRunLaneConfig,
    load_lane_config,
    resolve_lane_config,
)


def test_valid_lane_configs_resolve_with_lane_identity(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    run = resolve_lane_config(_run_config(), component_registry=registry, expected_lane="run")
    train = resolve_lane_config(_train_config(), component_registry=registry, expected_lane="train")

    assert run.lane == "run"
    assert run.config.strategy.id == "demo.strategy"
    assert train.lane == "train"
    assert train.config.labeler.id == "demo.label"
    assert train.config.model.id == "tests.sklearn_logistic"
    assert run.manifest()["lane"] == "run"


def test_strategy_run_lane_config_round_trips_through_resolver(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    config = StrategyRunLaneConfig(
        name="typed_strategy_demo",
        strategy=RunSourceRefConfig(source="component", id="demo.strategy"),
        indicators=[RunIndicatorSourceConfig(source="component", ids=["demo.indicator"])],
        ranking=RankingConfig(metric="sharpe_ratio", direction="desc"),
        portfolio=PortfolioConfig(entry_budget=1.0),
    )

    resolved = resolve_lane_config(config, component_registry=registry, expected_lane="run")

    assert resolved.config.indicators[0].ids == ["demo.indicator"]


def test_load_lane_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "lane.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "lane: run",
                "name: duplicate_lane",
                "strategy: {}",
                "strategy: {}",
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
        (
            "run",
            {"strategy": {"source": "component", "id": "demo.strategy", "import": "x.y"}},
            "strategy.import",
        ),
        (
            "run",
            {"strategy": {"source": "component", "id": "demo.strategy", "path": "strategy.py"}},
            "strategy.path",
        ),
        (
            "run",
            {"strategy": {"source": "component", "id": "demo.strategy", "params": {"window": 5}}},
            "strategy.params",
        ),
        (
            "run",
            {
                "indicators": [
                    {
                        "source": "playbook",
                        "ids": ["ma_explore"],
                        "notebook_path": "../unsafe.ipynb",
                    }
                ]
            },
            "indicators[0].notebook_path",
        ),
        (
            "train",
            {"labeler": {"id": "demo.label", "params": {"n": 5}}},
            "labeler.params",
        ),
        (
            "train",
            {
                "labeler": {
                    "id": "demo.label",
                    "artifact_path": "runs/previous-run/strategy_run.json",
                }
            },
            "labeler.artifact_path",
        ),
        (
            "train",
            {"labeler": {"id": "demo.label", "python": "lambda x: x"}},
            "labeler.python",
        ),
    ],
)
def test_lane_configs_reject_inline_code_and_arbitrary_paths(
    tmp_path: Path,
    lane: str,
    mutations: dict[str, object],
    expected_path: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = {"run": _run_config(), "train": _train_config()}[lane]
    raw = _merge(raw, mutations)

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane=lane)

    assert expected_path in str(error.value)
    assert "not allowed" in str(error.value) or "unknown field" in str(error.value)


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
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "model" in str(error.value)
    assert "aerd run --train" in str(error.value)


def test_strategy_run_rejects_top_level_train_block(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "train": {
                "label": {"source": "component", "id": "demo.label"},
                "model": {"source": "plugin", "id": "tests.sklearn_logistic"},
            }
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "train" in str(error.value)
    assert "aerd run --train" in str(error.value)


def test_run_indicator_selection_rejects_config_params(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {"indicators": [{"source": "component", "ids": "all", "params": {"path": "x.py"}}]},
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "indicators[0].params" in str(error.value)
    assert "unknown field" in str(error.value)


def test_run_all_component_indicator_ref_rejects_expanded_duplicates(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "indicators": [
                {"source": "component", "ids": "all"},
                {"source": "component", "ids": ["demo.indicator"]},
            ]
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "indicators[1].ids[0]" in str(error.value)
    assert "duplicates expanded component indicator id" in str(error.value)


def test_run_lane_rejects_unimplemented_failure_policy(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"failure_policy": "continue"})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "failure_policy" in str(error.value)


@pytest.mark.parametrize(
    "csv_path",
    ["/tmp/prices.csv", "../prices.csv", "~/prices.csv", "~user/prices.csv", "C:\\prices.csv"],
)
def test_lane_csv_source_rejects_non_project_relative_path(
    tmp_path: Path,
    csv_path: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_train_config(), {"data": {"source": "csv", "path": csv_path}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="train")

    assert "data.path" in str(error.value)
    assert "relative path" in str(error.value)


def test_lane_output_dir_rejects_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = _component_registry(tmp_path)
    outside = tmp_path / "outside-runs"
    outside.mkdir()
    (tmp_path / "runs").symlink_to(outside, target_is_directory=True)
    raw = _merge(_run_config(), {"output_dir": "runs"})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "output_dir" in str(error.value)
    assert "symlink" in str(error.value)


def test_run_lane_accepts_playbook_and_component_indicator_sources_together(
    tmp_path: Path,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "strategy": {"source": "playbook", "id": "strategy_explore"},
            "indicators": [
                {"source": "playbook", "ids": ["ma_explore"]},
                {"source": "component", "ids": "all"},
            ],
        },
    )

    resolved = resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert resolved.config.strategy.source == "playbook"
    assert [ref.source for ref in resolved.config.indicators] == ["playbook", "component"]


def test_train_rejects_strategy_sweep_config_with_missing_training_contract(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "missing_training_contract",
        "strategy": {"source": "component", "id": "demo.strategy"},
        "portfolio": {"entry_budget": 1.0},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="train")

    assert "train" in str(error.value)
    assert "train mode" in str(error.value)


@pytest.mark.parametrize(
    ("ranking", "expected"),
    [
        ({"metric": "not_a_metric", "direction": "desc"}, "ranking.metric"),
        ({"metric": "total_return", "direction": "sideways"}, "ranking.direction"),
        ({"metric": "total_return"}, "ranking.direction"),
    ],
)
def test_lane_ranking_metric_and_direction_validation(
    tmp_path: Path,
    ranking: dict[str, str],
    expected: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = ranking

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert expected in str(error.value)


def test_lane_ranking_accepts_vbt_metric_ids_and_secondary_metrics(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "total_return",
        "direction": "desc",
        "secondary_metrics": ["sharpe_ratio", "max_dd"],
    }

    resolved = resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert resolved.config.ranking.metric == "total_return"
    assert resolved.config.ranking.secondary_metrics == ["sharpe_ratio", "max_dd"]
    assert resolved.metric_registry is not None
    assert len(resolved.manifest()["metric_registry_fingerprint"]) == 64


def test_run_lane_accepts_dynamic_vbt_splitter_config(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "split": {
                "method": "from_rolling",
                "params": {"length": 20, "split": 0.8},
                "max_splits": 10,
            }
        },
    )

    resolved = resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert resolved.config.split is not None
    assert resolved.config.split.method == "from_rolling"
    assert resolved.config.split.params == {"length": 20, "split": 0.8}
    assert resolved.config.split.max_splits == 10


def test_run_lane_accepts_purged_kfold_splitter_method(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {"split": {"method": "from_purged_kfold", "params": {"n_folds": 4}}},
    )

    resolved = resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert resolved.config.split is not None
    assert resolved.config.split.method == "from_purged_kfold"


def test_run_lane_rejects_unknown_splitter_method(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"split": {"method": "walk_forward", "params": {}}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "split.method" in str(error.value)
    assert "from_rolling" in str(error.value)


def test_run_lane_rejects_unknown_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {"split": {"method": "from_rolling", "params": {"length": 20, "made_up": 1}}},
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "split.params.made_up" in str(error.value)


def test_run_lane_rejects_missing_required_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"split": {"method": "from_rolling", "params": {}}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "split.params.length" in str(error.value)
    assert "is required" in str(error.value)


def test_run_lane_rejects_splitter_method_requiring_runtime_object(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"split": {"method": "from_split_func", "params": {}}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "split.method" in str(error.value)
    assert "split_func" in str(error.value)


def test_run_lane_rejects_internal_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "split": {
                "method": "from_rolling",
                "params": {"length": 20, "template_context": {"x": "y"}},
            }
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "split.params.template_context" in str(error.value)
    assert "managed internally" in str(error.value)


@pytest.mark.parametrize(
    ("secondary_metrics", "expected"),
    [
        ("sharpe_ratio", "ranking.secondary_metrics"),
        (["sharpe_ratio", "sharpe_ratio"], "duplicate secondary metric"),
        (["total_return"], "must not repeat primary metric"),
        (["not_a_metric"], "ranking.secondary_metrics[0]"),
        ([{"id": "sharpe_ratio"}], "must be a non-empty metric id string"),
    ],
)
def test_lane_ranking_rejects_invalid_secondary_metrics(
    tmp_path: Path,
    secondary_metrics: object,
    expected: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "total_return",
        "direction": "desc",
        "secondary_metrics": secondary_metrics,
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert expected in str(error.value)


def test_lane_ranking_rejects_removed_rank_by_mode(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "total_return",
        "direction": "desc",
        "rank_by": "baseline_delta",
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "ranking.rank_by" in str(error.value)
    assert "secondary_metrics" in str(error.value)


def test_lane_ranking_rejects_secondary_only_metric_as_primary(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "baseline_delta", "direction": "desc"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="run")

    assert "primary-eligible" in str(error.value)


def test_train_lane_rejects_ranking_block(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _train_config()
    raw["ranking"] = {"metric": "total_return", "direction": "desc"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_lane_config(raw, component_registry=registry, expected_lane="train")

    assert "ranking" in str(error.value)
    assert "unknown field" in str(error.value)


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "strategy_demo",
        "data": {"source": "synthetic", "rows": 50, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "strategy": {"source": "component", "id": "demo.strategy"},
        "indicators": [{"source": "component", "ids": ["demo.indicator"]}],
        "ranking": {"metric": "sharpe_ratio", "direction": "desc"},
    }


def _train_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "train_demo",
        "data": {"source": "synthetic", "rows": 50, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "labeler": {"id": "demo.label"},
        "indicators": [{"source": "component", "ids": ["demo.indicator"]}],
        "train": {
            "model": {"source": "plugin", "id": "tests.sklearn_logistic"},
        },
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
        "# %% component overview\n"
        "# Lane-config fixture component used only for registry validation.\n"
        "# Source: static metadata; callable execution is not part of these tests.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return no output because lane-config tests only validate selection."""\n'
        "    pass\n"
    )


def _manifest_for(family: str, component_id: str) -> dict[str, object]:
    base = {"family": family, "id": component_id, "version": "1.0.0"}
    if family == "labels":
        return {
            **base,
            "input_names": ["Close"],
            "target_role": "supervised_target",
            "target_kind": "binary_classification",
            "output_names": ["labels"],
            "split_safety": {"purging_required": True},
        }
    if family == "indicators":
        return {
            **base,
            "input_names": ["Close"],
            "param_names": ["window"],
            "output_names": ["value"],
            "default_outputs": ["value"],
            "default_model_features": [{"output": "value", "transform": "identity"}],
            "supported_transforms": ["identity"],
        }
    if family == "strategies":
        return {
            **base,
            "input_names": ["Close"],
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
