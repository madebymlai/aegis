"""Unit tests for the top-level ``lock:`` Run Config block.

A Run Config may carry a top-level ``lock: {run_id, candidate_id}`` block that
reproduces one prior Candidate. The builder produces a typed ``Lock`` value object;
a malformed/incomplete ``lock:`` fails at validation; and (interim rule) a config that
carries both a top-level ``lock:`` and any per-Component ``params:`` is rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    Lock,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)


@pytest.fixture
def registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _raw_config(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "locked_run",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"target_exposure_cap": 1.0},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 40, "offset": 40, "split": 0.5},
                "max_splits": 2,
            },
        },
    }
    raw.update(overrides)
    return raw


def test_builder_produces_typed_lock(registry) -> None:
    resolved = resolve_run_config(
        _raw_config(lock={"run_id": "run-a", "candidate_id": "cand_123"}),
        component_registry=registry,
    )
    assert resolved.config.lock == Lock(run_id="run-a", candidate_id="cand_123")


def test_config_without_lock_has_none_lock(registry) -> None:
    resolved = resolve_run_config(_raw_config(), component_registry=registry)
    assert resolved.config.lock is None


def test_incomplete_lock_missing_candidate_id_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock={"run_id": "run-a"}),
            component_registry=registry,
        )
    paths = {issue.path for issue in excinfo.value.issues}
    assert "lock.candidate_id" in paths


def test_malformed_lock_not_a_mapping_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock="run-a"),
            component_registry=registry,
        )
    assert any(issue.path == "lock" for issue in excinfo.value.issues)


def test_lock_unknown_field_fails_validation(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(lock={"run_id": "run-a", "candidate_id": "c", "rank": 1}),
            component_registry=registry,
        )
    assert any(issue.path == "lock.rank" for issue in excinfo.value.issues)


def test_lock_with_component_params_rejected_interim(registry) -> None:
    with pytest.raises(ConfigValidationError) as excinfo:
        resolve_run_config(
            _raw_config(
                lock={"run_id": "run-a", "candidate_id": "c"},
                strategy={"id": "demo.strategy", "params": {"unused": 1}},
            ),
            component_registry=registry,
        )
    assert any(
        "lock" in issue.message and "params" in issue.message for issue in excinfo.value.issues
    )
