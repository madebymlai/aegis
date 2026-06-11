from __future__ import annotations

import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import write_strategy_component


def _base_config(execute: dict[str, object] | None = None) -> dict:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "p10",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 80, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0},
        "strategy": {"id": "demo.strategy"},
        "indicators": [],
        "ranking": {"metric": "total_return", "direction": "desc"},
        "optimization": {
            "search": "grid",
            "split": {"method": "from_rolling", "params": {"length": 20, "split": 0.5}},
            **({"execute": execute} if execute is not None else {}),
        },
    }


def test_optimization_execute_rejects_reserved_random_subset_key(tmp_path) -> None:
    raw = _base_config(execute={"random_subset": 5})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml", component_registry=_registry(tmp_path))


def test_optimization_execute_rejects_reserved_seed_key(tmp_path) -> None:
    raw = _base_config(execute={"seed": 42})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml", component_registry=_registry(tmp_path))


def test_optimization_execute_rejects_reserved_merge_func_key(tmp_path) -> None:
    raw = _base_config(execute={"merge_func": "row_stack"})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml", component_registry=_registry(tmp_path))


def test_optimization_rejects_removed_evidence_field(tmp_path) -> None:
    raw = _base_config()
    raw["optimization"]["evidence"] = {"return_grid": "off"}
    with pytest.raises(ConfigValidationError, match=r"optimization\.evidence"):
        resolve_run_config(
            raw, raw_text="", source_path="run.yaml", component_registry=_registry(tmp_path)
        )


def _registry(tmp_path):
    root = tmp_path / "research" / "components"
    write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)
