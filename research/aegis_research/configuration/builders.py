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
)


def _build_run_config(
    raw: dict[str, Any],
    *,
    data_config: DataConfig | None = None,
    portfolio_config: PortfolioConfig | None = None,
    report_config: ReportConfig | None = None,
    optimization_config: OptimizationConfig | None = None,
    strategy_config: RunSourceRefConfig | None = None,
    indicator_configs: list[RunIndicatorSourceConfig] | None = None,
    ranking_config: RankingConfig | None = None,
    lock_config: Lock | None = None,
) -> RunConfig:
    # Pydantic-ported sections are validated + constructed by the coordinator.
    # If they weren't constructed (validation failure short-circuit), raise.
    if data_config is None:
        raise ValueError("data_config required")
    if portfolio_config is None:
        raise ValueError("portfolio_config required")
    if report_config is None:
        raise ValueError("report_config required")
    if strategy_config is None:
        raise ValueError("strategy_config required")
    if indicator_configs is None:
        raise ValueError("indicator_configs required")
    if ranking_config is None:
        raise ValueError("ranking_config required")
    return RunConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=data_config,
        portfolio=portfolio_config,
        report=report_config,
        strategy=strategy_config,
        indicators=indicator_configs,
        ranking=ranking_config,
        optimization=optimization_config,
        lock=lock_config,
        output_dir=raw.get("output_dir", "runs"),
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
