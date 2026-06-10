"""Optimization validation — pydantic v2 structural tests.

Tests are driven through the coordinator (``resolve_run_config``) for
all-errors-at-once reporting and through ``TypeAdapter`` construction for
single-field structural checks. Assertions use pydantic's wording.

The per-section optimization validator module is deleted; validation lives on
the pydantic dataclass (``@model_validator``) and in the split-method prepass
inside the coordinator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    OptimizationConfig,
    RunSplitConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import write_strategy_component

# ── helpers ──────────────────────────────────────────────────────────────────

_OPTIMIZATION_ADAPTER = TypeAdapter(OptimizationConfig)
_SPLIT_ADAPTER = TypeAdapter(RunSplitConfig)

_SPLIT = {"method": "from_rolling", "params": {"length": 20, "split": 0.5}, "max_splits": 10}


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _resolve(optimization: dict[str, Any] | None, *, tmp_path: Path):
    """Resolve a minimal valid Run Config with the given optimization section."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [],
        "ranking": {"metric": "total_return"},
    }
    if optimization is not None:
        raw["optimization"] = optimization
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


# ── structural validation (TypeAdapter construction) ─────────────────────────


def test_optimization_construction_requires_search() -> None:
    with pytest.raises(ValidationError) as e:
        _OPTIMIZATION_ADAPTER.validate_python({"split": _SPLIT})
    assert any(err["loc"] == ("search",) for err in e.value.errors())


def test_optimization_construction_requires_split() -> None:
    with pytest.raises(ValidationError) as e:
        _OPTIMIZATION_ADAPTER.validate_python({"search": "grid"})
    assert any(err["loc"] == ("split",) for err in e.value.errors())


def test_optimization_construction_rejects_unknown_search() -> None:
    with pytest.raises(ValidationError) as e:
        _OPTIMIZATION_ADAPTER.validate_python({"search": "exhaustive", "split": _SPLIT})
    assert any(err["loc"] == ("search",) for err in e.value.errors())
    search_errors = [err for err in e.value.errors() if err["loc"] == ("search",)]
    assert search_errors
    assert "grid" in search_errors[0]["msg"] or "literal" in search_errors[0].get("type", "")


def test_optimization_construction_accepts_grid_without_subset_or_seed() -> None:
    config = _OPTIMIZATION_ADAPTER.validate_python({"search": "grid", "split": _SPLIT})
    assert config.random_subset is None
    assert config.seed is None


def test_optimization_construction_accepts_random_with_subset_and_seed() -> None:
    config = _OPTIMIZATION_ADAPTER.validate_python(
        {"search": "random", "split": _SPLIT, "random_subset": 100, "seed": 42}
    )
    assert config.random_subset == 100
    assert config.seed == 42


def test_run_split_construction_accepts_defaults() -> None:
    config = _SPLIT_ADAPTER.validate_python({"method": "from_rolling"})
    assert config.params == {}
    assert config.max_splits == 100


def test_run_split_construction_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError) as e:
        _SPLIT_ADAPTER.validate_python({"method": "from_rolling", "bogus": 42})
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


# ── search == "random" invariants (model_validator on OptimizationConfig) ─────


def test_random_search_requires_random_subset(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "random", "split": _SPLIT, "seed": 42}, tmp_path=tmp_path)
    issues = [(i.path, i.message) for i in e.value.issues]
    assert ("optimization", "Value error, random_subset is required when optimization.search is 'random'") in issues


def test_random_search_requires_seed(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "random", "split": _SPLIT, "random_subset": 100}, tmp_path=tmp_path)
    issues = [(i.path, i.message) for i in e.value.issues]
    assert (
        "optimization",
        "Value error, seed is required when optimization.search is 'random' so sampled evidence is deterministic",
    ) in issues


def test_random_search_requires_both_subset_and_seed_reports_first_missing(tmp_path: Path) -> None:
    """When both are missing, the first model_validator check fails (random_subset).

    pydantic ``@model_validator(mode="after")`` raises at the first ValueError;
    a second missing field is not reached. This is acceptable — the user fixes
    one and re-runs.
    """
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "random", "split": _SPLIT}, tmp_path=tmp_path)
    assert any(
        i.path == "optimization" and "random_subset" in i.message
        for i in e.value.issues
    )


def test_grid_search_rejects_random_subset(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "grid", "split": _SPLIT, "random_subset": 10}, tmp_path=tmp_path)
    issues = [(i.path, i.message) for i in e.value.issues]
    assert (
        "optimization",
        "Value error, random_subset is only valid when optimization.search is 'random'",
    ) in issues


# ── execute reserved keys (model_validator on OptimizationConfig) ─────────────


def test_execute_rejects_reserved_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "grid", "split": _SPLIT, "execute": {"seed": 1}}, tmp_path=tmp_path)
    assert any(
        i.path == "optimization" and "reserved keys" in i.message
        for i in e.value.issues
    )


# ── split.params.set_labels (model_validator on RunSplitConfig) ───────────────


def test_split_rejects_set_labels(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {"search": "grid", "split": {"method": "from_rolling", "params": {"set_labels": ["a", "b"], "length": 20, "split": 0.5}}},
            tmp_path=tmp_path,
        )
    issues = [(i.path, i.message) for i in e.value.issues]
    assert any(
        path == "optimization.split" and "set roles are owned by Aegis" in msg
        for path, msg in issues
    )


# ── optimization required (legacy top-level check) ───────────────────────────


def test_optimization_section_is_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(None, tmp_path=tmp_path)
    assert any(
        i.path == "optimization" and "is required" in i.message
        for i in e.value.issues
    )


# ── extra keys (pydantic extra="forbid") ──────────────────────────────────────


def test_optimization_rejects_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"search": "grid", "split": _SPLIT, "evidence": {"return_grid": "off"}}, tmp_path=tmp_path)
    issues = [(i.path, i.message) for i in e.value.issues]
    assert any(
        path == "optimization.evidence" and "unexpected keyword argument" in msg.lower()
        for path, msg in issues
    )


def test_optimization_must_be_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve("not_a_dict", tmp_path=tmp_path)
    issues = [(i.path, i.message) for i in e.value.issues]
    assert ("optimization", "Input should be a dictionary or an instance of OptimizationConfig") in issues
