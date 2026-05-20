from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    CandidateGridConfig,
    DataConfig,
    DataQualityConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    SignalConfig,
    SourceRefConfig,
    SplitConfig,
    StrategyRunLaneConfig,
    TrainLaneConfig,
    TrainModelConfig,
)


def _build_strategy_run_lane_config(raw: dict[str, Any]) -> StrategyRunLaneConfig:
    return StrategyRunLaneConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        lane="run",
        data=_build_data_config(raw.get("data", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        strategy=_build_run_source_ref(raw["strategy"]),
        indicators=_build_run_indicator_sources(raw["indicators"]),
        ranking=_build_ranking(raw["ranking"]),
        candidate_grid=CandidateGridConfig(**raw.get("candidate_grid", {})),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_train_lane_config(raw: dict[str, Any]) -> TrainLaneConfig:
    train = raw["train"]
    return TrainLaneConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        lane="train",
        data=_build_data_config(raw.get("data", {})),
        indicators=_build_run_indicator_sources(raw["indicators"]),
        split=SplitConfig(**train.get("split", {})),
        signals=SignalConfig(**train.get("signals", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        label=_build_source_ref(train["label"]),
        model=_build_train_model(train["model"]),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_train_model(raw: dict[str, Any]) -> TrainModelConfig:
    return TrainModelConfig(
        source=raw["source"],
        id=raw["id"],
        min_train_samples=raw.get("min_train_samples", 100),
        params=dict(raw.get("params", {})),
    )


def _build_source_ref(raw: dict[str, Any]) -> SourceRefConfig:
    return SourceRefConfig(source=raw["source"], id=raw["id"])


def _build_run_source_ref(raw: dict[str, Any]) -> RunSourceRefConfig:
    return RunSourceRefConfig(source=raw["source"], id=raw["id"])


def _build_run_indicator_sources(raw: list[dict[str, Any]]) -> list[RunIndicatorSourceConfig]:
    refs: list[RunIndicatorSourceConfig] = []
    for item in raw:
        ids = item["ids"]
        if ids == "all":
            refs.append(RunIndicatorSourceConfig(source=item["source"], ids="all"))
            continue
        refs.append(RunIndicatorSourceConfig(source=item["source"], ids=list(ids)))
    return refs


def _build_ranking(raw: dict[str, Any]) -> RankingConfig:
    return RankingConfig(
        metric=raw["metric"],
        direction=raw["direction"],
        rank_by=raw.get("rank_by", "primary_metric"),
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
