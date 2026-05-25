from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    RunSplitConfig,
    load_run_config,
    resolve_run_config,
)


def test_valid_run_config_resolves_without_lane_identity(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    resolved = resolve_run_config(_run_config(), component_registry=registry)

    assert resolved.config.strategy.id == "demo.strategy"
    assert "lane" not in resolved.manifest()


def test_run_config_round_trips_through_resolver(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    config = RunConfig(
        name="typed_strategy_demo",
        strategy=RunSourceRefConfig(id="demo.strategy"),
        indicators=[RunIndicatorSourceConfig(id="demo.indicator")],
        ranking=RankingConfig(metric="sharpe_ratio", direction="desc"),
        portfolio=PortfolioConfig(target_exposure_cap=1.0),
        optimization=OptimizationConfig(
            search="grid",
            split=RunSplitConfig(
                method="from_rolling",
                params={"length": 20, "offset": 20, "split": 0.5},
            ),
        ),
    )

    resolved = resolve_run_config(config, component_registry=registry)

    assert resolved.config.indicators[0].id == "demo.indicator"


def test_load_run_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "name: duplicate_run",
                "strategy: {}",
                "strategy: {}",
                "portfolio:",
                "  target_exposure_cap: 1.0",
            ]
        )
    )

    with pytest.raises(ConfigValidationError, match="duplicate mapping key"):
        load_run_config(path)


@pytest.mark.parametrize(
    ("mutations", "expected_path"),
    [
        (
            {"strategy": {"id": "demo.strategy", "import": "x.y"}},
            "strategy.import",
        ),
        (
            {"strategy": {"id": "demo.strategy", "path": "strategy.py"}},
            "strategy.path",
        ),
        (
            {"strategy": {"id": "demo.strategy", "params": {"window": 5}}},
            "strategy.params",
        ),
        (
            {
                "indicators": [
                    {
                        "id": "demo.indicator",
                        "notebook_path": "../unsafe.ipynb",
                    }
                ]
            },
            "indicators[0].notebook_path",
        ),
    ],
)
def test_run_configs_reject_inline_code_and_arbitrary_paths(
    tmp_path: Path,
    mutations: dict[str, object],
    expected_path: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), mutations)

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert expected_path in str(error.value)
    assert (
        "not allowed" in str(error.value)
        or "unknown field" in str(error.value)
        or "params must be declared by the component manifest" in str(error.value)
    )


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        ({"lane": "run"}, "lane"),
        ({"lane": "train"}, "lane"),
        ({"train": {"model": {"source": "plugin", "id": "demo.model"}}}, "train"),
        ({"model": {"plugin_id": "demo.model"}}, "model"),
        ({"labeler": {"id": "demo.label"}}, "labeler"),
        ({"labels": {"source": "component", "id": "demo.label"}}, "labels"),
        ({"signals": {"execution_timing": "next_open"}}, "signals"),
    ],
)
def test_run_config_rejects_removed_train_and_lane_fields(
    tmp_path: Path,
    mutation: dict[str, object],
    expected_path: str,
) -> None:
    registry = _component_registry(tmp_path)

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(_merge(_run_config(), mutation), component_registry=registry)

    assert expected_path in str(error.value)
    assert "single run config contract" in str(error.value)


def test_run_indicator_selection_rejects_config_params(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {"indicators": [{"id": "demo.indicator", "params": {"path": "x.py"}}]},
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "indicators[0].params" in str(error.value)
    assert "not allowed" in str(error.value)


def test_run_indicator_ref_rejects_duplicate_component_ids(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {
            "indicators": [
                {"id": "demo.indicator"},
                {"id": "demo.indicator"},
            ]
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "indicators[1].id" in str(error.value)
    assert "duplicates indicator component id" in str(error.value)


def test_run_config_rejects_unimplemented_failure_policy(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"failure_policy": "continue"})

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "failure_policy" in str(error.value)


@pytest.mark.parametrize(
    "csv_path",
    ["/tmp/prices.csv", "../prices.csv", "~/prices.csv", "~user/prices.csv", "C:\\prices.csv"],
)
def test_run_csv_source_rejects_non_project_relative_path(
    tmp_path: Path,
    csv_path: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(_run_config(), {"data": {"source": "csv", "path": csv_path}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "data.path" in str(error.value)
    assert "relative path" in str(error.value)


def test_run_output_dir_rejects_symlink_escape(
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
        resolve_run_config(raw, component_registry=registry)

    assert "output_dir" in str(error.value)
    assert "symlink" in str(error.value)


@pytest.mark.parametrize(
    ("ranking", "expected"),
    [
        ({"metric": "not_a_metric", "direction": "desc"}, "ranking.metric"),
        ({"metric": "total_return", "direction": "sideways"}, "ranking.direction"),
        ({"metric": "total_return"}, "ranking.direction"),
    ],
)
def test_run_ranking_metric_and_direction_validation(
    tmp_path: Path,
    ranking: dict[str, str],
    expected: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = ranking

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert expected in str(error.value)


def test_run_ranking_accepts_vbt_metric_ids_and_secondary_metrics(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "total_return",
        "direction": "desc",
        "secondary_metrics": ["sharpe_ratio", "max_dd"],
    }

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.ranking.metric == "total_return"
    assert resolved.config.ranking.secondary_metrics == ["sharpe_ratio", "max_dd"]
    assert resolved.metric_registry is not None
    assert len(resolved.manifest()["metric_registry_fingerprint"]) == 64


def test_run_accepts_dynamic_vbt_splitter_config(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split(
        {
            "method": "from_rolling",
            "params": {"length": 20, "split": 0.8},
            "max_splits": 10,
        }
    )

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.split.method == "from_rolling"
    assert resolved.config.optimization.split.params == {"length": 20, "split": 0.8}
    assert resolved.config.optimization.split.max_splits == 10


def test_run_accepts_purged_kfold_splitter_method(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split({"method": "from_purged_kfold", "params": {"n_folds": 4}})

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.split.method == "from_purged_kfold"


def test_run_rejects_unknown_splitter_method(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split({"method": "walk_forward", "params": {}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "optimization.split.method" in str(error.value)
    assert "from_rolling" in str(error.value)


def test_run_rejects_unknown_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split(
        {"method": "from_rolling", "params": {"length": 20, "made_up": 1}}
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "optimization.split.params.made_up" in str(error.value)


def test_run_rejects_missing_required_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split({"method": "from_rolling", "params": {}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "optimization.split.params.length" in str(error.value)
    assert "is required" in str(error.value)


def test_run_rejects_splitter_method_requiring_runtime_object(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split({"method": "from_split_func", "params": {}})

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "optimization.split.method" in str(error.value)
    assert "split_func" in str(error.value)


def test_run_rejects_internal_splitter_param(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config_with_split(
        {
            "method": "from_rolling",
            "params": {"length": 20, "template_context": {"x": "y"}},
        }
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "optimization.split.params.template_context" in str(error.value)
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
def test_run_ranking_rejects_invalid_secondary_metrics(
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
        resolve_run_config(raw, component_registry=registry)

    assert expected in str(error.value)


def test_run_ranking_rejects_removed_rank_by_mode(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "total_return",
        "direction": "desc",
        "rank_by": "baseline_delta",
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "ranking.rank_by" in str(error.value)
    assert "secondary_metrics" in str(error.value)


def test_run_ranking_rejects_secondary_only_metric_as_primary(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "baseline_delta", "direction": "desc"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "primary-eligible" in str(error.value)


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "strategy_demo",
        "data": {"source": "synthetic", "rows": 50, "arrays": ["OHLCV"]},
        "portfolio": {"target_exposure_cap": 1.0},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.indicator"}],
        "ranking": {"metric": "sharpe_ratio", "direction": "desc"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 20, "offset": 20, "split": 0.5},
            },
        },
    }


def _run_config_with_split(split: dict[str, object]) -> dict[str, object]:
    raw = _run_config()
    raw["optimization"] = {"search": "grid", "split": split}
    return raw


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.indicator")
    _write_component(root / "strategies" / "strategy.py", "strategies", "demo.strategy")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_component(path: Path, family: str, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_for(family, component_id)
    path.write_text(
        "# %% component overview\n"
        "# Run-config fixture component used only for registry validation.\n"
        "# Source: static metadata; callable execution is not part of these tests.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return no output because run-config tests only validate selection."""\n'
        "    pass\n"
    )


def _manifest_for(family: str, component_id: str) -> dict[str, object]:
    base = {"family": family, "id": component_id, "version": "1.0.0"}
    if family == "indicators":
        return {
            **base,
            "input_names": ["Close"],
            "param_names": ["window"],
            "output_names": ["value"],
            "defaults": {"window": 2},
            "wide_callable": "run_wide",
        }
    if family == "strategies":
        return {
            **base,
            "input_names": ["Close"],
            "output_name": "active",
            "owns_portfolio": False,
            "wide_callable": "run_wide",
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
