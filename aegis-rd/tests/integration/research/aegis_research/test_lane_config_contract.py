from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    load_run_config,
    resolve_run_config,
)
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_ranking_config,
    make_run_config,
    make_run_indicator_source_config,
    make_run_source_ref_config,
    make_run_split_config,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
)


def test_valid_run_config_resolves_without_lane_identity(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)

    resolved = resolve_run_config(_run_config(), component_registry=registry)

    assert resolved.config.strategy.id == "demo.strategy"
    assert "lane" not in resolved.manifest()


def test_run_config_resolves_from_raw_dict(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    config = make_run_config(
        name="typed_strategy_demo",
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.indicator")],
        ranking=make_ranking_config(metric="sharpe_ratio"),
        portfolio=make_portfolio_config(gross_cap=1.0, direction="longonly"),
        optimization=make_optimization_config(
            search="grid",
            split=make_run_split_config(
                method="from_rolling",
                params={"length": 20, "offset": 20, "split": 0.5},
            ),
        ),
    )

    resolved = resolve_run_config(to_builtin(config), component_registry=registry)

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
                "  gross_cap: 1.0",
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
        or "Unexpected keyword argument" in str(error.value)
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
    assert "Unexpected keyword argument" in str(error.value)


def test_run_indicator_selection_rejects_config_params(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _merge(
        _run_config(),
        {"indicators": [{"id": "demo.indicator", "params": {"path": "x.py"}}]},
    )

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "indicators[0].params" in str(error.value)
    assert "params must be declared by the component manifest" in str(error.value)


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


def test_run_ranking_rejects_unknown_metric(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "not_a_metric"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "ranking.metric" in str(error.value)


@pytest.mark.parametrize("removed_field", ["direction", "secondary_metrics"])
def test_run_ranking_rejects_removed_fields_as_unknown(
    tmp_path: Path,
    removed_field: str,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "total_return", removed_field: "desc"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert f"ranking.{removed_field}" in str(error.value)


def test_run_ranking_accepts_vbt_metric_id(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "total_return"}

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.ranking.metric == "total_return"
    assert resolved.metric_registry is not None
    assert len(resolved.manifest()["metric_registry_fingerprint"]) == 64


def test_run_ranking_rejects_removed_min_weight(tmp_path: Path) -> None:
    # EB shrinkage is parameter-free: the retired min_weight knob is an unknown
    # field and must be rejected rather than silently ignored.
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "sharpe_ratio", "min_weight": 0.5}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "min_weight" in str(error.value)


def test_run_ranking_defaults_min_trades_to_zero(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.ranking.min_trades == 0


def test_run_ranking_accepts_explicit_min_trades(tmp_path: Path) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {"metric": "sharpe_ratio", "min_trades": 20}

    resolved = resolve_run_config(raw, component_registry=registry)

    assert resolved.config.ranking.min_trades == 20


@pytest.mark.parametrize("bad_min_trades", [-1, 2.5, "10", True])
def test_run_ranking_rejects_invalid_min_trades(
    tmp_path: Path,
    bad_min_trades: object,
) -> None:
    registry = _component_registry(tmp_path)
    raw = _run_config()
    raw["ranking"] = {
        "metric": "sharpe_ratio",
        "min_trades": bad_min_trades,
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=registry)

    assert "ranking.min_trades" in str(error.value)


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


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "strategy_demo",
        "data": native_data_config_payload(end="2024-02-20"),
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.indicator"}],
        "ranking": {"metric": "sharpe_ratio"},
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
        }
    if family == "strategies":
        return {
            **base,
            "input_names": ["Close"],
            "output_name": "active",
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
