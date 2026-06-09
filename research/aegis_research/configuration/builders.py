from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    DataConfig,
    DataQualityConfig,
    Lock,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    RunSplitConfig,
)


def _build_run_config(
    raw: dict[str, Any],
    *,
    portfolio_config: PortfolioConfig | None = None,
    report_config: ReportConfig | None = None,
    ranking_config: RankingConfig | None = None,
    lock_config: Lock | None = None,
) -> RunConfig:
    # Pydantic-ported sections (portfolio, report, ranking, lock) are validated +
    # constructed by the coordinator. Raise if any were not constructed (validation
    # failure short-circuit).
    if portfolio_config is None:
        raise ValueError("portfolio_config required")
    if report_config is None:
        raise ValueError("report_config required")
    if ranking_config is None:
        raise ValueError("ranking_config required")
    return RunConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=_build_data_config(raw.get("data", {})),
        portfolio=portfolio_config,
        report=report_config,
        strategy=_build_run_source_ref(raw["strategy"]),
        indicators=_build_run_indicator_sources(raw["indicators"]),
        ranking=ranking_config,
        optimization=_build_optimization(raw.get("optimization")),
        lock=lock_config,
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_run_source_ref(raw: dict[str, Any]) -> RunSourceRefConfig:
    return RunSourceRefConfig(
        id=raw["id"],
        params=dict(raw.get("params", {})),
    )


def _build_run_indicator_sources(raw: list[dict[str, Any]]) -> list[RunIndicatorSourceConfig]:
    refs: list[RunIndicatorSourceConfig] = []
    for item in raw:
        refs.append(
            RunIndicatorSourceConfig(
                id=item["id"],
                params=dict(item.get("params", {})),
            )
        )
    return refs


def _build_run_split(raw: dict[str, Any] | None) -> RunSplitConfig | None:
    if raw is None:
        return None
    return RunSplitConfig(
        method=raw["method"],
        params=dict(raw.get("params", {})),
        max_splits=raw.get("max_splits", 100),
        max_estimated_output_cells=raw.get("max_estimated_output_cells", 25_000_000),
        max_public_artifact_bytes=raw.get("max_public_artifact_bytes", 10_000_000),
    )


def _build_optimization(raw: dict[str, Any] | None) -> OptimizationConfig | None:
    if raw is None:
        return None
    split = _build_run_split(raw["split"])
    if split is None:
        raise ValueError("optimization.split is required")
    return OptimizationConfig(
        search=raw["search"],
        split=split,
        random_subset=raw.get("random_subset"),
        seed=raw.get("seed"),
        execute=dict(raw.get("execute", {})),
    )


def _build_data_config(raw: dict[str, Any]) -> DataConfig:
    value = dict(raw)
    quality = value.get("quality", {})
    if isinstance(quality, DataQualityConfig):
        quality_config = quality
    else:
        quality_config = DataQualityConfig(**quality)
    value["quality"] = quality_config
    return DataConfig(**value)
