from __future__ import annotations

import pytest

from research.aegis_research.config import resolve_run_config
from research.aegis_research.configuration.schema import ConfigValidationError


def _base_config(execute: dict[str, object] | None = None) -> dict:
    return {
        "schema_version": 5,
        "name": "p10",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 80, "arrays": ["OHLCV"]},
        "portfolio": {"entry_budget": 1.0},
        "strategy": {"source": "playbook", "id": "x"},
        "indicators": [],
        "ranking": {"metric": "total_return", "direction": "desc"},
        "optimization": {
            "search": "grid",
            "split": {"method": "from_rolling", "params": {"length": 20, "split": 0.5}},
            **({"execute": execute} if execute is not None else {}),
        },
    }


def test_optimization_execute_rejects_reserved_random_subset_key() -> None:
    raw = _base_config(execute={"random_subset": 5})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml")


def test_optimization_execute_rejects_reserved_seed_key() -> None:
    raw = _base_config(execute={"seed": 42})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml")


def test_optimization_execute_rejects_reserved_merge_func_key() -> None:
    raw = _base_config(execute={"merge_func": "row_stack"})
    with pytest.raises(ConfigValidationError, match="reserved keys"):
        resolve_run_config(raw, raw_text="", source_path="run.yaml")


def test_optimization_evidence_return_grid_off_is_accepted() -> None:
    raw = _base_config()
    raw["optimization"]["evidence"] = {"return_grid": "off"}
    resolved = resolve_run_config(raw, raw_text="", source_path="run.yaml")
    assert resolved.config.optimization.evidence.return_grid == "off"
