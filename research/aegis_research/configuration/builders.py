from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    DataConfig,
    DataQualityConfig,
    OptimizationConfig,
    OptimizationEvidenceConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    RunSplitConfig,
)


def _build_run_config(raw: dict[str, Any]) -> RunConfig:
    return RunConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=_build_data_config(raw.get("data", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        strategy=_build_run_source_ref(raw["strategy"]),
        indicators=_build_run_indicator_sources(raw["indicators"]),
        ranking=_build_ranking(raw["ranking"]),
        optimization=_build_optimization(raw.get("optimization")),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_run_source_ref(raw: dict[str, Any]) -> RunSourceRefConfig:
    return RunSourceRefConfig(
        id=raw["id"],
        lock_id=raw.get("lock_id"),
        candidate_id=raw.get("candidate_id"),
        run_id=raw.get("run_id"),
        params=dict(raw.get("params", {})),
    )


def _build_run_indicator_sources(raw: list[dict[str, Any]]) -> list[RunIndicatorSourceConfig]:
    refs: list[RunIndicatorSourceConfig] = []
    for item in raw:
        refs.append(
            RunIndicatorSourceConfig(
                id=item["id"],
                lock_id=item.get("lock_id"),
                candidate_id=item.get("candidate_id"),
                run_id=item.get("run_id"),
                params=dict(item.get("params", {})),
            )
        )
    return refs


def _build_ranking(raw: dict[str, Any]) -> RankingConfig:
    return RankingConfig(
        metric=raw["metric"],
        direction=raw["direction"],
        secondary_metrics=list(raw.get("secondary_metrics", [])),
    )


def _build_run_split(raw: dict[str, Any] | None) -> RunSplitConfig | None:
    if raw is None:
        return None
    return RunSplitConfig(
        method=raw["method"],
        params=dict(raw.get("params", {})),
        max_splits=raw.get("max_splits", 100),
        max_estimated_output_cells=raw.get("max_estimated_output_cells", 25_000_000),
        max_public_artifact_bytes=raw.get("max_public_artifact_bytes", 10_000_000),
        max_batch_expansion_bytes=raw.get("max_batch_expansion_bytes", 2_000_000_000),
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
        evidence=_build_optimization_evidence(raw.get("evidence", {})),
    )


def _build_optimization_evidence(raw: dict[str, Any]) -> OptimizationEvidenceConfig:
    return OptimizationEvidenceConfig(return_grid=raw.get("return_grid", "first"))


def _build_data_config(raw: dict[str, Any]) -> DataConfig:
    value = dict(raw)
    quality = value.get("quality", {})
    if isinstance(quality, DataQualityConfig):
        quality_config = quality
    else:
        quality_config = DataQualityConfig(**quality)
    value["quality"] = quality_config
    return DataConfig(**value)
