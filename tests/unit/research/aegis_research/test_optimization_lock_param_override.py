"""Unit tests for the locked-Run params-override Evidence.

When a top-level ``lock:`` overlays a tuning config (ADR-0006 lock-wins), the locked
Candidate's params take effect and any per-Component ``params:`` the author declared are
overridden. This module turns those overridden ``params:`` into a fail-loud Evidence
record — Component identity, the parameter names, and the ignored values — so the Run's
Manifest never silently misrepresents what ran.
"""

from __future__ import annotations

from research.aegis_research.config import (
    RankingConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.optimization.lock_param_override import (
    overridden_component_params,
)


def _config(
    *,
    strategy_params: dict | None = None,
    indicator_params: dict | None = None,
) -> RunConfig:
    return RunConfig(
        name="locked_overlay",
        strategy=RunSourceRefConfig(id="demo.strategy", params=strategy_params or {}),
        indicators=[
            RunIndicatorSourceConfig(id="demo.returns", params=indicator_params or {})
        ],
        ranking=RankingConfig(metric="total_return"),
    )


def test_no_component_params_yields_no_overrides() -> None:
    assert overridden_component_params(_config()) == []


def test_strategy_params_recorded_as_override() -> None:
    overrides = overridden_component_params(_config(strategy_params={"threshold": 2.0}))
    assert overrides == [
        {
            "family": "strategies",
            "component_id": "demo.strategy",
            "slot": "strategy",
            "param_names": ["threshold"],
            "ignored_values": {"threshold": 2.0},
        }
    ]


def test_indicator_params_recorded_with_component_slot() -> None:
    overrides = overridden_component_params(
        _config(indicator_params={"window": 5})
    )
    assert overrides == [
        {
            "family": "indicators",
            "component_id": "demo.returns",
            "slot": "demo.returns",
            "param_names": ["window"],
            "ignored_values": {"window": 5},
        }
    ]


def test_param_names_are_sorted_for_stable_evidence() -> None:
    overrides = overridden_component_params(
        _config(strategy_params={"b": 2, "a": 1})
    )
    assert overrides[0]["param_names"] == ["a", "b"]
    assert overrides[0]["ignored_values"] == {"a": 1, "b": 2}
