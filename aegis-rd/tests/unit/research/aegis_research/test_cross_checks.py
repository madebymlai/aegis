"""Registry cross-check tests driven through the module's public seam.

Every test calls ``cross_check_registries`` directly with an in-memory
component registry (from the test factory), a metric registry, and either a
factory-built ``RunConfig`` or a raw dict. No tmp dirs, no component files,
no discovery.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.component_registry.contracts import ComponentDefinition
from research.aegis_research.component_registry.registry import FrozenComponentRegistry
from research.aegis_research.configuration import ConfigValidationIssue
from research.aegis_research.configuration.cross_checks import cross_check_registries
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from tests.support.research.aegis_research.factories import (
    make_component_registry,
    make_indicator_component_definition,
    make_ranking_config,
    make_run_config,
    make_run_indicator_source_config,
    make_run_source_ref_config,
    make_strategy_component_definition,
)

# ═══════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _indicator(
    *,
    id: str = "demo.signal",
    input_names: tuple[str, ...] = ("Close",),
    param_names: tuple[str, ...] = ("window",),
    output_names: tuple[str, ...] = ("value",),
    defaults: dict[str, object] | None = None,
    has_param_space: bool = False,
) -> ComponentDefinition:
    return make_indicator_component_definition(
        id=id,
        input_names=input_names,
        param_names=param_names,
        output_names=output_names,
        defaults=defaults or {},
        has_param_space=has_param_space,
    )


def _strategy(
    *,
    id: str = "demo.strategy",
    input_names: tuple[str, ...] = ("Close",),
    param_names: tuple[str, ...] = ("lookback",),
    output_name: str = "active",
    consumes_outputs: tuple[str, ...] = ("value",),
    defaults: dict[str, object] | None = None,
    has_param_space: bool = False,
) -> ComponentDefinition:
    return make_strategy_component_definition(
        id=id,
        input_names=input_names,
        param_names=param_names,
        output_name=output_name,
        consumes_outputs=consumes_outputs,
        defaults=defaults or {},
        has_param_space=has_param_space,
    )


def _component_registry(
    indicators: dict[str, ComponentDefinition] | None = None,
    strategies: dict[str, ComponentDefinition] | None = None,
) -> FrozenComponentRegistry:
    return make_component_registry(
        {
            "indicators": indicators or {},
            "strategies": strategies or {},
        }
    )


def _default_component_registry() -> FrozenComponentRegistry:
    """Registry with one strategy and one indicator that satisfy output contract."""
    return _component_registry(
        indicators={"demo.signal": _indicator(param_names=(), output_names=("value",))},
        strategies={"demo.strategy": _strategy(param_names=(), consumes_outputs=("value",))},
    )


def _default_metric_registry() -> FrozenMetricRegistry:
    from research.aegis_research.metrics import make_default_metric_registry

    return make_default_metric_registry()


def _issues_by_path(
    issues: list[ConfigValidationIssue],
) -> dict[str, list[str]]:
    """Group issue messages by path for easy assertions."""
    result: dict[str, list[str]] = {}
    for issue in issues:
        result.setdefault(issue.path, []).append(issue.message)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# full dialect: strategy membership
# ═══════════════════════════════════════════════════════════════════════════════


def test_strategy_accepts_known_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_strategy_rejects_unknown_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="missing.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.id" in by_path
    assert any("unknown strategy component id" in msg for msg in by_path["strategy.id"])


def test_strategy_rejects_all_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="all"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.id" in by_path
    assert any("must select one component id" in msg for msg in by_path["strategy.id"])


# ═══════════════════════════════════════════════════════════════════════════════
# full dialect: indicator membership
# ═══════════════════════════════════════════════════════════════════════════════


def test_indicator_accepts_known_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_indicator_rejects_unknown_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="missing.indicator")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[0].id" in by_path
    assert any("unknown indicator component id" in msg for msg in by_path["indicators[0].id"])


def test_indicator_rejects_all_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="all")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[0].id" in by_path
    assert any("must select one component id" in msg for msg in by_path["indicators[0].id"])


def test_indicators_flag_duplicate_component_id() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[
            make_run_indicator_source_config(id="demo.signal"),
            make_run_indicator_source_config(id="demo.signal"),
        ],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[1].id" in by_path
    assert any("duplicates indicator component id" in msg for msg in by_path["indicators[1].id"])


# ═══════════════════════════════════════════════════════════════════════════════
# full dialect: output contract
# ═══════════════════════════════════════════════════════════════════════════════


def test_strategy_rejects_missing_consumed_indicator_output() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.consumes_outputs" in by_path
    assert any("not produced" in msg for msg in by_path["strategy.consumes_outputs"])


def test_strategy_accepts_indicators_producing_consumed_outputs() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_output_contract_detects_duplicate_produced_outputs() -> None:
    reg = _component_registry(
        indicators={
            "demo.one": _indicator(id="demo.one", output_names=("dupe",), param_names=()),
            "demo.two": _indicator(id="demo.two", output_names=("dupe",), param_names=()),
        },
        strategies={
            "demo.strategy": _strategy(consumes_outputs=("dupe",), param_names=()),
        },
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[
            make_run_indicator_source_config(id="demo.one"),
            make_run_indicator_source_config(id="demo.two"),
        ],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[1].id" in by_path
    assert any("duplicates produced indicator output" in msg for msg in by_path["indicators[1].id"])


# ═══════════════════════════════════════════════════════════════════════════════
# full dialect: component params
# ═══════════════════════════════════════════════════════════════════════════════


def test_params_unknown_rejected_on_strategy() -> None:
    reg = _component_registry(
        indicators={"demo.signal": _indicator(param_names=(), output_names=("value",))},
        strategies={"demo.strategy": _strategy(param_names=("lookback",))},
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy", params={"unknown": 5}),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.params" in by_path
    assert any(
        "params must be declared by the component manifest" in msg
        for msg in by_path["strategy.params"]
    )


def test_params_unknown_rejected_on_indicator() -> None:
    reg = _component_registry(
        indicators={"demo.signal": _indicator(param_names=("window",), output_names=("value",))},
        strategies={"demo.strategy": _strategy(param_names=(), consumes_outputs=("value",))},
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal", params={"unknown": 5})],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[0].params" in by_path
    assert any(
        "params must be declared by the component manifest" in msg
        for msg in by_path["indicators[0].params"]
    )


def test_params_missing_satisfied_by_default() -> None:
    reg = _component_registry(
        indicators={"demo.signal": _indicator(param_names=(), output_names=("value",))},
        strategies={
            "demo.strategy": _strategy(
                param_names=("lookback", "threshold"),
                defaults={"threshold": 0.5},
                consumes_outputs=("value",),
            ),
        },
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy", params={"lookback": 20}),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_params_missing_rejected_when_not_defaulted() -> None:
    reg = _component_registry(
        indicators={"demo.signal": _indicator(param_names=(), output_names=("value",))},
        strategies={
            "demo.strategy": _strategy(
                param_names=("lookback", "threshold"), consumes_outputs=("value",)
            )
        },
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy", params={"lookback": 20}),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy" in by_path
    assert any("must provide params" in msg for msg in by_path["strategy"])


def test_params_waived_by_param_space_function() -> None:
    reg = _component_registry(
        indicators={"demo.signal": _indicator(param_names=(), output_names=("value",))},
        strategies={
            "demo.strategy": _strategy(
                param_names=("lookback", "threshold"),
                has_param_space=True,
                consumes_outputs=("value",),
            ),
        },
    )
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy", params={}),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=reg,
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


# ═══════════════════════════════════════════════════════════════════════════════
# full dialect: metric membership
# ═══════════════════════════════════════════════════════════════════════════════


def test_ranking_accepts_known_metric() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="total_return"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_ranking_rejects_unknown_metric() -> None:
    config = make_run_config(
        strategy=make_run_source_ref_config(id="demo.strategy"),
        indicators=[make_run_indicator_source_config(id="demo.signal")],
        ranking=make_ranking_config(metric="not_a_metric"),
    )
    issues = cross_check_registries(
        config,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "ranking.metric" in by_path
    assert any("must be one of" in msg for msg in by_path["ranking.metric"])


# ═══════════════════════════════════════════════════════════════════════════════
# raw dialect: best-effort membership
# ═══════════════════════════════════════════════════════════════════════════════


def test_raw_strategy_rejects_unknown_id() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "missing.strategy"},
        "indicators": [{"id": "demo.signal"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.id" in by_path
    assert any("unknown strategy component id" in msg for msg in by_path["strategy.id"])


def test_raw_indicator_rejects_unknown_id() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "missing.indicator"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[0].id" in by_path
    assert any("unknown indicator component id" in msg for msg in by_path["indicators[0].id"])


def test_raw_strategy_rejects_all_id() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "all"},
        "indicators": [{"id": "demo.signal"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "strategy.id" in by_path
    assert any("must select one component id" in msg for msg in by_path["strategy.id"])


def test_raw_indicator_rejects_all_id() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "all"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[0].id" in by_path
    assert any("must select one component id" in msg for msg in by_path["indicators[0].id"])


def test_raw_indicators_flag_duplicate_component_id() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.signal"}, {"id": "demo.signal"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "indicators[1].id" in by_path
    assert any("duplicates indicator component id" in msg for msg in by_path["indicators[1].id"])


def test_raw_ranking_rejects_unknown_metric() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.signal"}],
        "ranking": {"metric": "not_a_metric"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    by_path = _issues_by_path(issues)
    assert "ranking.metric" in by_path
    assert any("must be one of" in msg for msg in by_path["ranking.metric"])


def test_raw_skips_non_mapping_strategy() -> None:
    raw: dict[str, Any] = {
        "strategy": "not_a_dict",
        "indicators": [{"id": "demo.signal"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_raw_skips_non_list_indicators() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": "not_a_list",
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []


def test_raw_accepts_valid_ids() -> None:
    raw: dict[str, Any] = {
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.signal"}],
        "ranking": {"metric": "total_return"},
    }
    issues = cross_check_registries(
        raw,
        component_registry=_default_component_registry(),
        metric_registry=_default_metric_registry(),
    )
    assert issues == []
