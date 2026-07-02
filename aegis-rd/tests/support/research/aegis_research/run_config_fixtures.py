from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    ResolvedRunConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)


def build_resolved_run_config(
    tmp_path: Path,
    *,
    output_dir: str | None = None,
    data: dict[str, Any] | None = None,
    optimization: dict[str, Any] | None = None,
) -> ResolvedRunConfig:
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    write_strategy_component(root / "strategies" / "strategy.py")
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "run_fixture",
        "output_dir": output_dir or "runs",
        "data": {
            "arrays": ["OHLCV"],
            "instruments": ["SYN.XNAS"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        },
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
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
    if data is not None:
        raw["data"] = {**raw["data"], **data}
    if optimization is not None:
        merged = {**raw["optimization"], **optimization}
        if "split" in optimization:
            merged["split"] = {**raw["optimization"]["split"], **optimization["split"]}
        raw["optimization"] = merged
    return resolve_run_config(
        raw,
        component_registry=discover_component_registry(root=root, repo_root=tmp_path),
    )
