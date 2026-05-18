from __future__ import annotations

from typing import Any

from research.aegis_research.configuration.schema import (
    DataConfig,
    DataQualityConfig,
    IndicatorConfig,
    IndicatorFeatureConfig,
    IndicatorSpecConfig,
    LabelConfig,
    LabelGeneratorConfig,
    LabelTargetConfig,
    LabelTargetSelectionConfig,
    LabelTargetTransformConfig,
    ModelConfig,
    PlayConfig,
    PlayLaneConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    SignalConfig,
    SourceRefConfig,
    SplitConfig,
    StrategyRunLaneConfig,
    TrainLaneConfig,
)


def _build_play_lane_config(raw: dict[str, Any]) -> PlayLaneConfig:
    play_raw = raw["play"]
    return PlayLaneConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        lane="play",
        data=_build_data_config(raw.get("data", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        play=PlayConfig(
            stages=list(play_raw["stages"]),
            indicator_refs=[_build_source_ref(item) for item in play_raw["indicator_refs"]],
            ranking=_build_ranking(play_raw["ranking"]),
            backup_last_run=play_raw.get("backup_last_run", False),
        ),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_strategy_run_lane_config(raw: dict[str, Any]) -> StrategyRunLaneConfig:
    return StrategyRunLaneConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        lane="run",
        data=_build_data_config(raw.get("data", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        strategy=_build_source_ref(raw["strategy"]),
        indicator_refs=[_build_source_ref(item) for item in raw["indicator_refs"]],
        ranking=_build_ranking(raw["ranking"]),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_train_lane_config(raw: dict[str, Any]) -> TrainLaneConfig:
    return TrainLaneConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        lane="train",
        data=_build_data_config(raw.get("data", {})),
        indicators=_build_indicator_config(raw.get("indicators", {})),
        split=SplitConfig(**raw.get("split", {})),
        signals=SignalConfig(**raw.get("signals", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        label=_build_source_ref(raw["label"]),
        model=ModelConfig(**raw["model"]),
        output_dir=raw.get("output_dir", "runs"),
    )


def _build_source_ref(raw: dict[str, Any]) -> SourceRefConfig:
    return SourceRefConfig(
        source=raw["source"],
        id=raw["id"],
        params=dict(raw.get("params", {})),
    )


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


def _build_indicator_config(raw: dict[str, Any]) -> IndicatorConfig:
    if not raw:
        return IndicatorConfig()
    default_config = IndicatorConfig()
    specs = raw.get("specs")
    return IndicatorConfig(
        invalid_value_policy=raw.get("invalid_value_policy", "drop_rows"),
        specs=default_config.specs
        if specs is None
        else [_build_indicator_spec(spec) for spec in specs],
    )


def _build_indicator_spec(raw: dict[str, Any]) -> IndicatorSpecConfig:
    definition = _indicator_registry()[raw["id"]]
    outputs = list(raw.get("outputs", definition.default_outputs))
    model_features = raw.get("model_features")
    if model_features is None:
        model_features = definition.default_model_features
    return IndicatorSpecConfig(
        id=raw["id"],
        params=dict(raw.get("params", {})),
        outputs=outputs,
        model_features=[
            IndicatorFeatureConfig(
                output=feature["output"],
                transform=feature.get("transform", "identity"),
            )
            for feature in model_features
        ],
        grid=raw.get("grid", "zipped"),
        param_product=raw.get("param_product", False),
    )


def _build_label_config(raw: dict[str, Any]) -> LabelConfig:
    generator_raw = raw.get("generator", {})
    kind = generator_raw.get("kind", "fixlb")
    generator_params = _default_label_generator_params(str(kind))
    generator_params.update(generator_raw.get("params", {}))
    generator = LabelGeneratorConfig(kind=str(kind), params=generator_params)

    target_raw = raw.get("target", {})
    transform_raw = target_raw.get("transform", {})
    transform_name = transform_raw.get("name") or _default_label_transform_name(generator)
    transform_params = _default_label_transform_params(str(transform_name))
    transform_params.update(transform_raw.get("params", {}))
    target = LabelTargetConfig(
        role=target_raw.get("role", "supervised_target"),
        source_output=target_raw.get("source_output", "labels"),
        select=LabelTargetSelectionConfig(
            params=dict(target_raw.get("select", {}).get("params", {}))
        ),
        transform=LabelTargetTransformConfig(
            name=str(transform_name),
            version=transform_raw.get("version", 1),
            params=transform_params,
        ),
    )
    return LabelConfig(generator=generator, target=target)


def _default_label_generator_params(kind: str) -> dict[str, Any]:
    if kind == "fixlb":
        return {"n": 5}
    if kind == "trendlb":
        return {"up_th": 0.1, "down_th": 0.1, "mode": "binary"}
    if kind == "pivotlb":
        return {"up_th": 0.1, "down_th": 0.1}
    return {}


def _default_label_transform_name(generator: LabelGeneratorConfig) -> str:
    if generator.kind == "fixlb":
        return "threshold_future_return"
    if generator.kind == "trendlb" and generator.params.get("mode", "binary") == "binary":
        return "identity_binary"
    if generator.kind == "trendlb":
        return "continuous_identity"
    if generator.kind == "pivotlb":
        return "positive_event"
    return "identity_binary"


def _default_label_transform_params(transform_name: str) -> dict[str, Any]:
    if transform_name == "threshold_future_return":
        return {"threshold": 0.0}
    if transform_name in {"identity_binary", "positive_event"}:
        return {"positive_value": 1}
    return {}


def _indicator_registry():
    from research.aegis_research import config as config_module

    return config_module.indicator_registry()
