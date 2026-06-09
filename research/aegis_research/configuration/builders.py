from __future__ import annotations

from dataclasses import fields
from typing import Any

from research.aegis_research.configuration.schema import (
    DEFAULT_LOCK_ROLE,
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
    split_lock_handle,
)


def _coerce_float_fields(raw: dict[str, Any], field_names: set[str]) -> None:
    """Coerce integer values to float for the named float-typed fields.

    ADR-0012: An integer YAML literal in a float field (e.g. ``gross_cap: 1``)
    is stored as an ``int`` and serialized as ``1``. Coerce it to ``1.0`` now so
    the subsequent pydantic ports are byte-neutral.
    """
    for name in field_names:
        if name in raw and isinstance(raw[name], int) and not isinstance(raw[name], bool):
            raw[name] = float(raw[name])


def _float_field_names(cls: type) -> set[str]:
    """Return the names of float-typed fields on a dataclass."""
    return {f.name for f in fields(cls) if f.type in (float, "float")}


def _build_run_config(
    raw: dict[str, Any],
    *,
    portfolio_config: PortfolioConfig | None = None,
    report_config: ReportConfig | None = None,
    strategy_config: RunSourceRefConfig | None = None,
    indicator_configs: list[RunIndicatorSourceConfig] | None = None,
) -> RunConfig:
    # Pydantic-ported sections are validated + constructed by the coordinator.
    # If they weren't constructed (validation failure short-circuit), raise.
    if portfolio_config is None:
        raise ValueError("portfolio_config required")
    if report_config is None:
        raise ValueError("report_config required")
    if strategy_config is None:
        raise ValueError("strategy_config required")
    if indicator_configs is None:
        raise ValueError("indicator_configs required")
    ranking_raw = dict(raw["ranking"])
    _coerce_float_fields(ranking_raw, _float_field_names(RankingConfig))
    return RunConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=_build_data_config(raw.get("data", {})),
        portfolio=portfolio_config,
        report=report_config,
        strategy=strategy_config,
        indicators=indicator_configs,
        ranking=_build_ranking(ranking_raw),
        optimization=_build_optimization(raw.get("optimization")),
        lock=_build_lock(raw.get("lock")),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_lock(raw: dict[str, Any] | str | None) -> Lock | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        run_id, role = split_lock_handle(raw)
        return Lock(run_id=run_id, candidate_id=role or DEFAULT_LOCK_ROLE)
    return Lock(run_id=raw["run_id"], candidate_id=raw["candidate_id"])


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


def _build_ranking(raw: dict[str, Any]) -> RankingConfig:
    return RankingConfig(
        metric=raw["metric"],
        min_weight=raw.get("min_weight", RankingConfig.min_weight),
        min_trades=raw.get("min_trades", RankingConfig.min_trades),
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
