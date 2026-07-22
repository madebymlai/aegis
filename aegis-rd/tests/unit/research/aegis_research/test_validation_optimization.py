"""Public optimization configuration permits only continuous replay policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    OptimizationConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import write_strategy_component
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
)

_ADAPTER = TypeAdapter(OptimizationConfig)
_BLOCK_BARS = 20


def _optimization(**overrides: Any) -> dict[str, Any]:
    return {
        "search": "grid",
        "observation_block_bars": _BLOCK_BARS,
        **overrides,
    }


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _resolve(optimization: object | None, *, tmp_path: Path):
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": native_data_config_payload(instruments=["SYN.XNAS"], end="2024-04-30"),
        "portfolio": {"direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [],
        "ranking": {"metric": "total_return"},
    }
    if optimization is not None:
        raw["optimization"] = optimization
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


def test_optimization_requires_search_and_observation_block_bars() -> None:
    with pytest.raises(ValidationError) as error:
        _ADAPTER.validate_python({})

    locations = {item["loc"] for item in error.value.errors()}
    assert ("search",) in locations
    assert ("observation_block_bars",) in locations


def test_grid_and_seeded_random_search_are_valid() -> None:
    grid = _ADAPTER.validate_python(_optimization())
    random = _ADAPTER.validate_python(_optimization(search="random", random_subset=100, seed=42))

    assert grid.observation_block_bars == _BLOCK_BARS
    assert random.random_subset == 100
    assert random.seed == 42


def test_observation_block_bars_must_be_positive() -> None:
    with pytest.raises(ValidationError) as error:
        _ADAPTER.validate_python(_optimization(observation_block_bars=0))

    assert any(item["loc"] == ("observation_block_bars",) for item in error.value.errors())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("split", {"method": "from_rolling"}),
        ("held_out_start", "2024-01-01"),
        ("warmup_bars", 20),
        ("scored_start", 20),
        ("max_splits", 10),
        ("max_estimated_output_cells", 1_000),
        ("max_public_artifact_bytes", 1_000),
        ("squeeze", False),
        ("fix_ranges", True),
        ("set_labels", ["selection", "held_out"]),
        ("iteration", "split_wise"),
        ("merge_func", "column_stack"),
        ("wrap_results", True),
        ("attach_bounds", True),
        ("right_inclusive", False),
    ],
)
def test_removed_split_warmup_and_vbt_policy_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        _ADAPTER.validate_python(_optimization(**{field: value}))

    assert any(
        item["loc"] == (field,) and item["type"] == "unexpected_keyword_argument"
        for item in error.value.errors()
    )


def test_random_search_requires_random_subset_and_seed(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as subset_error:
        _resolve(_optimization(search="random", seed=42), tmp_path=tmp_path)
    assert any("random_subset is required" in issue.message for issue in subset_error.value.issues)

    with pytest.raises(ConfigValidationError) as seed_error:
        _resolve(_optimization(search="random", random_subset=100), tmp_path=tmp_path)
    assert any("seed is required" in issue.message for issue in seed_error.value.issues)


def test_grid_search_rejects_random_subset(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        _resolve(_optimization(random_subset=10), tmp_path=tmp_path)

    assert any("random_subset is only valid" in issue.message for issue in error.value.issues)


def test_execute_is_rejected_as_a_removed_field(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        _resolve(_optimization(execute={"seed": 1}), tmp_path=tmp_path)

    assert any(
        issue.path == "optimization.execute" and issue.message == "Unexpected keyword argument"
        for issue in error.value.issues
    )


def test_optimization_section_is_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        _resolve(None, tmp_path=tmp_path)

    assert any(
        issue.path == "optimization" and "is required" in issue.message
        for issue in error.value.issues
    )


def test_optimization_must_be_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        _resolve("not_a_dict", tmp_path=tmp_path)

    assert any(issue.path == "optimization" for issue in error.value.issues)


def test_random_subset_and_seed_ranges_are_validated() -> None:
    with pytest.raises(ValidationError) as subset_error:
        _ADAPTER.validate_python(_optimization(search="random", random_subset=0, seed=7))
    assert any(item["loc"] == ("random_subset",) for item in subset_error.value.errors())

    with pytest.raises(ValidationError) as seed_error:
        _ADAPTER.validate_python(_optimization(search="random", random_subset=16, seed=-1))
    assert any(item["loc"] == ("seed",) for item in seed_error.value.errors())
