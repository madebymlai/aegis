from __future__ import annotations

import pytest

from research.aegis_research.metrics import (
    SOURCE_TYPE_VBT_STATS,
    MetricDefinition,
    MetricRegistry,
    MetricRegistryError,
    make_default_metric_registry,
)
from research.aegis_research.metrics.custom import register_custom_metrics
from research.aegis_research.metrics.custom.baseline_delta import baseline_delta_value
from research.aegis_research.metrics.stats import register_vbt_stats_metrics


def test_metric_registry_freezes_definitions_and_fingerprint() -> None:
    registry = MetricRegistry()
    registry.register(_definition("sharpe_ratio", title="Sharpe Ratio"))
    registry.register(_definition("total_return", title="Total Return"))

    frozen = registry.freeze()

    assert frozen.ids() == ("sharpe_ratio", "total_return")
    assert frozen.get("total_return").title == "Total Return"
    assert len(frozen.fingerprint) == 64


def test_metric_registry_rejects_duplicate_ids() -> None:
    registry = MetricRegistry()
    registry.register(_definition("total_return"))

    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        registry.register(_definition("total_return"))


def test_metric_registry_rejects_malformed_definition() -> None:
    registry = MetricRegistry()

    with pytest.raises(MetricRegistryError, match="metric id must be non-empty"):
        registry.register(_definition(""))


def test_frozen_metric_registry_definitions_are_immutable() -> None:
    registry = MetricRegistry()
    registry.register(_definition("total_return"))
    frozen = registry.freeze()

    with pytest.raises(TypeError):
        frozen.definitions["sharpe_ratio"] = _definition("sharpe_ratio")  # type: ignore[index]


def test_metric_registry_fingerprint_is_order_independent() -> None:
    first = MetricRegistry()
    first.register(_definition("total_return", title="Total Return"))
    first.register(_definition("sharpe_ratio", title="Sharpe Ratio"))
    second = MetricRegistry()
    second.register(_definition("sharpe_ratio", title="Sharpe Ratio"))
    second.register(_definition("total_return", title="Total Return"))

    assert first.freeze().fingerprint == second.freeze().fingerprint

    changed = MetricRegistry()
    changed.register(_definition("total_return", title="Total Return [%]"))
    changed.register(_definition("sharpe_ratio", title="Sharpe Ratio"))

    assert first.freeze().fingerprint != changed.freeze().fingerprint


def test_default_metric_registry_contains_supported_stats_and_custom_metrics() -> None:
    registry = make_default_metric_registry()

    assert {
        "total_return",
        "max_dd",
        "total_trades",
        "win_rate",
        "total_fees_paid",
        "sharpe_ratio",
        "baseline_delta",
    }.issubset(registry.ids())
    assert registry.get("total_return").target == "portfolio"
    assert registry.get("baseline_delta").primary_eligible is False
    assert registry.get("baseline_delta").secondary_eligible is True


def test_vbt_stats_registration_uses_current_metric_titles() -> None:
    registry = MetricRegistry()

    register_vbt_stats_metrics(
        registry,
        portfolio_metrics={
            "total_return": {"title": "Return From Test"},
            "max_dd": {"title": "Drawdown From Test"},
            "total_trades": {"title": "Trades From Test"},
            "win_rate": {"title": "Win Rate From Test"},
            "total_fees_paid": {"title": "Fees From Test"},
            "sharpe_ratio": {"title": "Sharpe From Test"},
        },
    )

    frozen = registry.freeze()
    assert frozen.get("total_return").title == "Return From Test"
    assert frozen.get("max_dd").direction_hint == "asc"


def test_vbt_stats_registration_fails_when_supported_metric_is_missing() -> None:
    registry = MetricRegistry()

    with pytest.raises(MetricRegistryError, match="Portfolio stats metric 'max_dd'"):
        register_vbt_stats_metrics(
            registry,
            portfolio_metrics={
                "total_return": {"title": "Total Return"},
            },
        )


def test_custom_metric_collision_with_vbt_metric_fails() -> None:
    registry = MetricRegistry()
    registry.register(_definition("baseline_delta", title="Colliding Baseline Delta"))

    with pytest.raises(MetricRegistryError, match="duplicate metric id"):
        register_custom_metrics(registry)


def test_baseline_delta_metric_calculation_uses_selected_primary_metric() -> None:
    record = {"baseline_metrics": {"total_return": 0.4}}

    assert baseline_delta_value(record, "total_return", 0.7) == pytest.approx(0.3)
    assert baseline_delta_value(record, "sharpe_ratio", 0.7) is None


def _definition(metric_id: str, *, title: str = "Total Return") -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        title=title,
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="larger_is_better",
        primary_eligible=True,
        secondary_eligible=True,
        direction_hint="desc",
        provider="vectorbtpro",
        target="portfolio",
        vbt_metric=metric_id,
        source_method="stats",
    )
