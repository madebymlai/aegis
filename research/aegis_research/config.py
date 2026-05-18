from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from research.aegis_research.indicator_registry import indicator_registry
from research.aegis_research.component_registry import (
    ComponentRegistryError,
    ComponentSelection,
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.model_registry import (
    FrozenModelRegistry,
    ModelRegistry,
    freeze_model_registry,
)

CONFIG_SCHEMA_VERSION = 2
EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

DATA_SOURCES = {"synthetic", "csv", "yfinance", "binance", "ccxt"}
REMOTE_DATA_SOURCES = {"yfinance", "binance", "ccxt"}
LABEL_KINDS = {"fixlb", "trendlb", "pivotlb"}
TRENDLB_MODES = {"binary", "binary_cont", "binary_cont_sat", "pct_change", "pct_change_norm"}
LABEL_TARGET_ROLES = {"supervised_target", "regime"}
LABEL_TARGET_TRANSFORMS = {
    "threshold_future_return",
    "identity_binary",
    "continuous_identity",
    "positive_event",
}
SPLIT_KINDS = {"purged_kfold"}
MODEL_DENIED_KEYS = {
    "class",
    "code",
    "estimator",
    "factory",
    "function",
    "import",
    "load",
    "loaded_model",
    "kind",
    "module",
    "mutable",
    "plugin",
    "python",
    "state",
    "update",
}
PORTFOLIO_TARGET_SIZE_TYPES = {
    "targetamount",
    "targetvalue",
    "targetpercent",
    "targetpercent100",
}
PORTFOLIO_DIRECTIONS = {"longonly"}
SIGNAL_POLICIES = {"long_only_hysteresis"}
SIGNAL_EXECUTION_TIMINGS = {"next_open", "same_close"}
MISSING_POLICIES = {"nan", "drop", "raise"}
OHLCV_FEATURE_MAP_KEYS = {"open", "high", "low", "close", "volume"}
DATA_QUALITY_DEGRADATIONS = {
    "duplicate_index",
    "missing_rows",
    "non_monotonic_index",
    "skipped_symbols",
}
REPORT_STATUS_SURVIVED = "survived"
REPORT_STATUS_REJECTED = "rejected"
REPORT_STATUS_NEEDS_MORE_EVIDENCE = "needs_more_evidence"
REPORT_STATUSES = {
    REPORT_STATUS_SURVIVED,
    REPORT_STATUS_REJECTED,
    REPORT_STATUS_NEEDS_MORE_EVIDENCE,
}
INDICATOR_INVALID_VALUE_POLICIES = {"drop_rows", "raise"}
INDICATOR_GRIDS = {"zipped", "product"}
INDICATOR_INLINE_CODE_KEYS = {
    "apply_func",
    "code",
    "formula",
    "function",
    "import",
    "module",
    "python",
}
LANES = {"play", "run", "train"}
SOURCE_KINDS = {"component", "playbook"}
PLAY_STAGES = {"labels", "indicators", "strategies"}
RANKING_DIRECTIONS = {"asc", "desc"}
LANE_EXECUTABLE_DENIED_KEYS = {
    "artifact_path",
    "callable",
    "class",
    "code",
    "formula",
    "function",
    "import",
    "last_run",
    "leaderboard_row",
    "load",
    "module",
    "notebook",
    "notebook_path",
    "path",
    "python",
    "script",
    "script_path",
}

SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|token|secret|password|access[_-]?key|private[_-]?key|"
    r"credential|authorization|client[_-]?secret)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(Bearer\s+\S+|Basic\s+\S+|(?:^|[?&;\s])(?:api[_-]?key|token|access[_-]?token|"
    r"secret|password|passphrase|signature|key|auth(?:orization)?)=|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|://[^\s:/]+:[^\s@]+@)",
    re.IGNORECASE,
)
DENIED_PASSTHROUGH_KEYS = {
    "auth",
    "authentication",
    "cookie",
    "cookies",
    "header",
    "headers",
    "proxy",
    "proxies",
    "session",
    "client",
    "transport",
    "cache",
    "cache_path",
    "cache_dir",
}


@dataclass(frozen=True)
class ConfigValidationIssue:
    path: str
    message: str


class ConfigValidationError(ValueError):
    def __init__(self, issues: list[ConfigValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"Invalid experiment config: {details}")


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    keys: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise ConfigValidationError([ConfigValidationIssue(str(key), "duplicate mapping key")])
        keys.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class DataQualityConfig:
    allowed_degradations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DataConfig:
    source: str = "synthetic"
    symbols: list[str] = field(default_factory=lambda: ["SYN"])
    start: str | None = None
    end: str | None = None
    timeframe: str = "1D"
    path: str | None = None
    seed: int = 42
    rows: int = 750
    missing_index: str = "raise"
    missing_columns: str = "raise"
    tz_localize: str | bool | None = None
    tz_convert: str | bool | None = None
    skip_on_error: bool = False
    silence_warnings: bool = False
    feature_map: dict[str, str] = field(default_factory=dict)
    quality: DataQualityConfig = field(default_factory=DataQualityConfig)
    wrapper_kwargs: dict[str, Any] = field(default_factory=dict)
    provider_kwargs: dict[str, Any] = field(default_factory=dict)
    execution_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndicatorFeatureConfig:
    output: str
    transform: str = "identity"


@dataclass(frozen=True)
class IndicatorSpecConfig:
    id: str
    params: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    model_features: list[IndicatorFeatureConfig] = field(default_factory=list)
    grid: str = "zipped"
    param_product: bool = False


@dataclass(frozen=True)
class IndicatorConfig:
    invalid_value_policy: str = "drop_rows"
    specs: list[IndicatorSpecConfig] = field(
        default_factory=lambda: [
            IndicatorSpecConfig(
                id="returns",
                params={"window": [1, 5, 20]},
                outputs=["returns"],
                model_features=[IndicatorFeatureConfig(output="returns")],
            ),
            IndicatorSpecConfig(
                id="ma",
                params={"window": [10, 30], "wtype": "simple"},
                outputs=["ma"],
                model_features=[IndicatorFeatureConfig(output="ma", transform="distance_to_close")],
            ),
            IndicatorSpecConfig(
                id="volatility",
                params={"window": [20]},
                outputs=["volatility"],
                model_features=[IndicatorFeatureConfig(output="volatility")],
            ),
            IndicatorSpecConfig(
                id="rsi",
                params={"window": [14], "wtype": "wilder"},
                outputs=["rsi"],
                model_features=[IndicatorFeatureConfig(output="rsi", transform="scale_0_1")],
            ),
        ]
    )


@dataclass(frozen=True)
class LabelGeneratorConfig:
    kind: str = "fixlb"
    params: dict[str, Any] = field(default_factory=lambda: {"n": 5})


@dataclass(frozen=True)
class LabelTargetSelectionConfig:
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LabelTargetTransformConfig:
    name: str = "threshold_future_return"
    version: int = 1
    params: dict[str, Any] = field(default_factory=lambda: {"threshold": 0.0})


@dataclass(frozen=True)
class LabelTargetConfig:
    role: str = "supervised_target"
    source_output: str = "labels"
    select: LabelTargetSelectionConfig = field(default_factory=LabelTargetSelectionConfig)
    transform: LabelTargetTransformConfig = field(default_factory=LabelTargetTransformConfig)


@dataclass(frozen=True)
class LabelConfig:
    generator: LabelGeneratorConfig = field(default_factory=LabelGeneratorConfig)
    target: LabelTargetConfig = field(default_factory=LabelTargetConfig)

    @property
    def kind(self) -> str:
        return self.generator.kind


@dataclass(frozen=True)
class SplitConfig:
    kind: str = "purged_kfold"
    n_folds: int = 5
    n_test_folds: int = 1
    purge_td: str | int | float = "0D"
    embargo_td: str | int | float = "0D"
    max_splits: int = 100
    max_estimated_output_cells: int = 25_000_000
    max_public_artifact_bytes: int = 10_000_000


@dataclass(frozen=True)
class ModelConfig:
    plugin_id: str | None = None
    min_train_samples: int = 100
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalConfig:
    policy: str = "long_only_hysteresis"
    long_entry_threshold: float = 0.55
    long_exit_threshold: float = 0.50
    execution_timing: str = "next_open"


@dataclass(frozen=True)
class PortfolioConfig:
    init_cash: float = 10_000.0
    fees: float = 0.001
    slippage: float = 0.0005
    entry_budget: float = 1.0
    direction: str = "longonly"


@dataclass(frozen=True)
class ReportConfig:
    min_oos_sharpe: float = 0.5
    max_oos_drawdown: float = 0.35
    min_oos_trades: int = 5
    freq: str = "1D"
    year_freq: str = "252D"


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    schema_version: int = CONFIG_SCHEMA_VERSION
    data: DataConfig = field(default_factory=DataConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    output_dir: str = "runs"


@dataclass(frozen=True)
class SourceRefConfig:
    source: str
    id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingConfig:
    metric: str
    direction: str
    rank_by: str = "primary_metric"


@dataclass(frozen=True)
class PlayConfig:
    stages: list[str]
    indicator_refs: list[SourceRefConfig]
    ranking: RankingConfig
    backup_last_run: bool = False


@dataclass(frozen=True)
class PlayLaneConfig:
    name: str
    schema_version: int = CONFIG_SCHEMA_VERSION
    lane: str = "play"
    data: DataConfig = field(default_factory=DataConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    play: PlayConfig | None = None
    output_dir: str = "runs"


@dataclass(frozen=True)
class StrategyRunLaneConfig:
    name: str
    strategy: SourceRefConfig
    indicator_refs: list[SourceRefConfig]
    ranking: RankingConfig
    schema_version: int = CONFIG_SCHEMA_VERSION
    lane: str = "run"
    data: DataConfig = field(default_factory=DataConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    output_dir: str = "runs"


@dataclass(frozen=True)
class TrainLaneConfig:
    name: str
    label: SourceRefConfig
    model: ModelConfig
    schema_version: int = CONFIG_SCHEMA_VERSION
    lane: str = "train"
    data: DataConfig = field(default_factory=DataConfig)
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    output_dir: str = "runs"


LaneConfig = PlayLaneConfig | StrategyRunLaneConfig | TrainLaneConfig


@dataclass(frozen=True)
class ConfigSelectionEvidence:
    source: str
    config_path: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "config_path": self.config_path,
        }


@dataclass(frozen=True)
class ResolvedExperimentConfig:
    config: ExperimentConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    model_registry: FrozenModelRegistry | None = None
    selection: ConfigSelectionEvidence | None = None

    def redacted_authored_config(self) -> dict[str, Any]:
        return redact_config(self.authored_config)

    def redacted_resolved_config(self) -> dict[str, Any]:
        return redact_config(to_builtin(asdict(self.config)))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
            "selection": self.selection.manifest() if self.selection else None,
        }


@dataclass(frozen=True)
class ResolvedLaneConfig:
    config: LaneConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None
    component_registry: FrozenComponentRegistry | None = None

    @property
    def lane(self) -> str:
        return self.config.lane

    def redacted_authored_config(self) -> dict[str, Any]:
        return redact_config(self.authored_config)

    def redacted_resolved_config(self) -> dict[str, Any]:
        return redact_config(to_builtin(asdict(self.config)))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "lane": self.config.lane,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
            "component_registry_fingerprint": (
                self.component_registry.fingerprint if self.component_registry else None
            ),
        }


def with_config_selection(
    config: ResolvedExperimentConfig,
    selection: ConfigSelectionEvidence,
    *,
    source_path: str | None = None,
) -> ResolvedExperimentConfig:
    return ResolvedExperimentConfig(
        config=config.config,
        raw_config_hash=config.raw_config_hash,
        authored_config=config.authored_config,
        source_path=config.source_path if source_path is None else source_path,
        model_registry=config.model_registry,
        selection=selection,
    )


def load_experiment_config(
    path: str | Path,
    *,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
) -> ResolvedExperimentConfig:
    config_path = Path(path)
    raw_text = config_path.read_text()
    raw = yaml.load(raw_text, Loader=_UniqueKeySafeLoader)
    return resolve_experiment_config(
        raw,
        raw_text=raw_text,
        source_path=str(path),
        model_registry=model_registry,
    )


def resolve_experiment_config(
    value: ResolvedExperimentConfig | ExperimentConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
) -> ResolvedExperimentConfig:
    frozen_registry = freeze_model_registry(model_registry)
    if isinstance(value, ResolvedExperimentConfig):
        if frozen_registry is not None:
            _assert_model_config_registered(value.config.model, frozen_registry)
            return ResolvedExperimentConfig(
                config=value.config,
                raw_config_hash=value.raw_config_hash,
                authored_config=value.authored_config,
                source_path=value.source_path,
                model_registry=frozen_registry,
                selection=value.selection,
            )
        return value

    if isinstance(value, ExperimentConfig):
        raw = to_builtin(asdict(value))
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            model_registry=frozen_registry,
        )

    return _build_resolved_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        model_registry=frozen_registry,
    )


def load_lane_config(
    path: str | Path,
    *,
    component_registry: FrozenComponentRegistry | None = None,
    expected_lane: str | None = None,
) -> ResolvedLaneConfig:
    config_path = Path(path)
    raw_text = config_path.read_text()
    raw = yaml.load(raw_text, Loader=_UniqueKeySafeLoader)
    return resolve_lane_config(
        raw,
        raw_text=raw_text,
        source_path=str(path),
        component_registry=component_registry,
        expected_lane=expected_lane,
    )


def resolve_lane_config(
    value: ResolvedLaneConfig | LaneConfig | dict[str, Any],
    *,
    raw_text: str | None = None,
    source_path: str | None = None,
    component_registry: FrozenComponentRegistry | None = None,
    expected_lane: str | None = None,
) -> ResolvedLaneConfig:
    if isinstance(value, ResolvedLaneConfig):
        if expected_lane is not None and value.lane != expected_lane:
            raise ConfigValidationError(
                [ConfigValidationIssue("lane", f"must be {expected_lane!r}")]
            )
        return value

    registry = component_registry or discover_component_registry()
    if isinstance(value, PlayLaneConfig | StrategyRunLaneConfig | TrainLaneConfig):
        raw = to_builtin(asdict(value))
        raw_text = yaml.safe_dump(raw, sort_keys=False)
        return _build_resolved_lane_config(
            raw,
            raw_text=raw_text,
            source_path=source_path,
            component_registry=registry,
            expected_lane=expected_lane,
        )

    return _build_resolved_lane_config(
        value,
        raw_text=raw_text,
        source_path=source_path,
        component_registry=registry,
        expected_lane=expected_lane,
    )


def _build_resolved_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    model_registry: FrozenModelRegistry | None,
) -> ResolvedExperimentConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError(
            [ConfigValidationIssue("$", "experiment config must be a mapping")]
        )

    issues: list[ConfigValidationIssue] = []
    _validate_raw_config(raw, issues, model_registry=model_registry)
    if issues:
        raise ConfigValidationError(issues)

    config = ExperimentConfig(
        name=raw["name"],
        schema_version=raw["schema_version"],
        data=_build_data_config(raw.get("data", {})),
        indicators=_build_indicator_config(raw.get("indicators", {})),
        labels=_build_label_config(raw.get("labels", {})),
        split=SplitConfig(**raw.get("split", {})),
        model=ModelConfig(**raw.get("model", {})),
        signals=SignalConfig(**raw.get("signals", {})),
        portfolio=PortfolioConfig(**raw.get("portfolio", {})),
        report=ReportConfig(**raw.get("report", {})),
        output_dir=raw.get("output_dir", "runs"),
    )
    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedExperimentConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        model_registry=model_registry,
        selection=None,
    )


def _build_resolved_lane_config(
    raw: dict[str, Any],
    *,
    raw_text: str | None,
    source_path: str | None,
    component_registry: FrozenComponentRegistry,
    expected_lane: str | None,
) -> ResolvedLaneConfig:
    if not isinstance(raw, dict):
        raise ConfigValidationError([ConfigValidationIssue("$", "lane config must be a mapping")])

    issues: list[ConfigValidationIssue] = []
    _validate_raw_lane_config(
        raw,
        issues,
        component_registry=component_registry,
        expected_lane=expected_lane,
    )
    if issues:
        raise ConfigValidationError(issues)

    lane = str(raw["lane"])
    if lane == "play":
        config: LaneConfig = _build_play_lane_config(raw)
    elif lane == "run":
        config = _build_strategy_run_lane_config(raw)
    elif lane == "train":
        config = _build_train_lane_config(raw)
    else:
        raise ConfigValidationError([ConfigValidationIssue("lane", f"must be one of {sorted(LANES)}")])

    text_for_hash = raw_text if raw_text is not None else yaml.safe_dump(raw, sort_keys=False)
    return ResolvedLaneConfig(
        config=config,
        raw_config_hash=hashlib.sha256(text_for_hash.encode()).hexdigest(),
        authored_config=to_builtin(raw),
        source_path=source_path,
        component_registry=component_registry,
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
    definition = indicator_registry()[raw["id"]]
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


def _validate_raw_lane_config(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    expected_lane: str | None,
) -> None:
    lane = raw.get("lane")
    _validate_known_keys("$", raw, _lane_allowed_top_level_keys(lane), issues)
    _require_int("schema_version", raw, issues, positive=True)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(ConfigValidationIssue("schema_version", f"must be {CONFIG_SCHEMA_VERSION}"))
    if _require_str("lane", raw, issues) and lane not in LANES:
        issues.append(ConfigValidationIssue("lane", f"must be one of {sorted(LANES)}"))
    if expected_lane is not None and lane != expected_lane:
        issues.append(ConfigValidationIssue("lane", f"must be {expected_lane!r}"))
    if _require_str("name", raw, issues):
        _validate_experiment_name(raw["name"], issues)
    _validate_output_dir(raw, issues)

    data = _section(raw, "data", set(DataConfig.__dataclass_fields__), issues)
    portfolio = _section(
        raw,
        "portfolio",
        set(PortfolioConfig.__dataclass_fields__) | {"size", "size_type"},
        issues,
    )
    report = _section(raw, "report", set(ReportConfig.__dataclass_fields__), issues)
    _validate_data(data, issues)
    _validate_portfolio(portfolio, issues)
    _validate_report(report, issues)

    if lane == "play":
        _validate_play_lane(raw, issues, component_registry=component_registry)
    elif lane == "run":
        _validate_strategy_run_lane(raw, issues, component_registry=component_registry)
    elif lane == "train":
        _validate_train_lane(raw, issues, component_registry=component_registry)


def _lane_allowed_top_level_keys(lane: Any) -> set[str]:
    common = {"schema_version", "lane", "name", "data", "portfolio", "report", "output_dir"}
    if lane == "play":
        return common | {"play"}
    if lane == "run":
        return common | {"strategy", "indicator_refs", "ranking", "failure_policy"}
    if lane == "train":
        return common | {"label", "indicators", "split", "model", "signals"}
    return common | {
        "play",
        "strategy",
        "indicator_refs",
        "ranking",
        "label",
        "indicators",
        "split",
        "model",
        "signals",
    }


def _validate_play_lane(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> None:
    play = _section(
        raw,
        "play",
        {"stages", "indicator_refs", "ranking", "backup_last_run"},
        issues,
    )
    _validate_no_lane_executable_keys("play", play, issues)
    _validate_play_stages(play, issues)
    _validate_source_ref_list(
        "play.indicator_refs",
        play.get("indicator_refs"),
        "indicators",
        issues,
        component_registry=component_registry,
        allow_component_all=True,
    )
    _validate_ranking("play.ranking", play.get("ranking"), issues)
    _optional_bool("play.backup_last_run", play, issues)


def _validate_strategy_run_lane(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> None:
    _validate_training_fields_absent(raw, issues)
    _validate_source_ref(
        "strategy",
        raw.get("strategy"),
        "strategies",
        issues,
        component_registry=component_registry,
    )
    _validate_source_ref_list(
        "indicator_refs",
        raw.get("indicator_refs"),
        "indicators",
        issues,
        component_registry=component_registry,
        allow_component_all=True,
    )
    _validate_ranking("ranking", raw.get("ranking"), issues)


def _validate_train_lane(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
) -> None:
    if "strategy" in raw or "ranking" in raw or "indicator_refs" in raw:
        issues.append(
            ConfigValidationIssue(
                "strategy",
                "strategy sweep config belongs to aerd run; train requires a training contract",
            )
        )
    _validate_source_ref(
        "label",
        raw.get("label"),
        "labels",
        issues,
        component_registry=component_registry,
    )
    indicators = _section(raw, "indicators", set(IndicatorConfig.__dataclass_fields__), issues)
    split = _section(raw, "split", set(SplitConfig.__dataclass_fields__), issues)
    model = _section(raw, "model", set(ModelConfig.__dataclass_fields__), issues)
    signals = _section(raw, "signals", set(SignalConfig.__dataclass_fields__), issues)
    _validate_indicators(indicators, issues)
    _validate_split(split, issues)
    _validate_model(model, issues, model_registry=None)
    _validate_signals(signals, issues)
    if not isinstance(model.get("plugin_id"), str) or not model.get("plugin_id"):
        issues.append(
            ConfigValidationIssue(
                "model.plugin_id",
                "is required for train lane training contract",
            )
        )


def _validate_training_fields_absent(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    for key in ("model", "labels", "label", "split"):
        if key in raw:
            issues.append(
                ConfigValidationIssue(
                    key,
                    "model training fields are not valid for strategy run; use aerd train",
                )
            )


def _validate_play_stages(play: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    stages = play.get("stages")
    if not _require_str_list("play.stages", stages, issues, non_empty=True):
        return
    for index, stage in enumerate(stages):
        if stage not in PLAY_STAGES:
            issues.append(
                ConfigValidationIssue(f"play.stages[{index}]", f"must be one of {sorted(PLAY_STAGES)}")
            )


def _validate_source_ref_list(
    path: str,
    value: Any,
    family: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    allow_component_all: bool = False,
) -> None:
    if not isinstance(value, list) or not value:
        issues.append(ConfigValidationIssue(path, "must be a non-empty list"))
        return
    for index, item in enumerate(value):
        _validate_source_ref(
            f"{path}[{index}]",
            item,
            family,
            issues,
            component_registry=component_registry,
            allow_component_all=allow_component_all,
        )


def _validate_source_ref(
    path: str,
    value: Any,
    family: str,
    issues: list[ConfigValidationIssue],
    *,
    component_registry: FrozenComponentRegistry,
    allow_component_all: bool = False,
) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"source", "id", "params"}, issues)
    _validate_no_lane_executable_keys(path, value, issues)
    source = value.get("source")
    if not isinstance(source, str) or source not in SOURCE_KINDS:
        issues.append(ConfigValidationIssue(f"{path}.source", f"must be one of {sorted(SOURCE_KINDS)}"))
        return
    component_id = value.get("id")
    if not isinstance(component_id, str):
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a string"))
        return
    if component_id == "" or component_id == "all":
        if source == "component" and allow_component_all:
            return
        issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty stable id"))
        return
    if not EXPERIMENT_NAME_RE.fullmatch(component_id):
        issues.append(
            ConfigValidationIssue(
                f"{path}.id",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )
    params = value.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(f"{path}.params", "must be a mapping"))
    else:
        _validate_json_like(f"{path}.params", params, issues)
        _validate_no_lane_executable_keys(f"{path}.params", params, issues)
    if source == "component":
        try:
            component_registry.get(ComponentSelection(family, component_id))
        except ComponentRegistryError:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.id",
                    f"unknown {family[:-1] if family.endswith('s') else family} component id",
                )
            )


def _validate_ranking(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, {"metric", "direction", "rank_by"}, issues)
    metric = value.get("metric")
    if not isinstance(metric, str) or not metric:
        issues.append(ConfigValidationIssue(f"{path}.metric", "must be a non-empty string"))
    elif metric not in _portfolio_metric_ids():
        issues.append(
            ConfigValidationIssue(f"{path}.metric", f"must be one of {sorted(_portfolio_metric_ids())}")
        )
    direction = value.get("direction")
    if not isinstance(direction, str) or direction not in RANKING_DIRECTIONS:
        issues.append(
            ConfigValidationIssue(f"{path}.direction", f"must be one of {sorted(RANKING_DIRECTIONS)}")
        )
    rank_by = value.get("rank_by", "primary_metric")
    if rank_by not in {"primary_metric", "baseline_delta"}:
        issues.append(
            ConfigValidationIssue(
                f"{path}.rank_by",
                "must be one of ['baseline_delta', 'primary_metric']",
            )
        )


def _portfolio_metric_ids() -> set[str]:
    from research.aegis_research.reports import PORTFOLIO_METRIC_CATALOG

    return set(PORTFOLIO_METRIC_CATALOG)


def _validate_no_lane_executable_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in LANE_EXECUTABLE_DENIED_KEYS:
                issues.append(
                    ConfigValidationIssue(
                        child_path,
                        "is not allowed in lane config; select trusted component or playbook IDs",
                    )
                )
            _validate_no_lane_executable_keys(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_lane_executable_keys(f"{path}[{index}]", item, issues)


def _validate_output_dir(raw: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    if not _optional_str("output_dir", raw, issues):
        return
    output_dir = raw.get("output_dir")
    if output_dir is None:
        return
    path = Path(str(output_dir))
    if path.is_absolute() or ".." in path.parts:
        issues.append(
            ConfigValidationIssue("output_dir", "must be a relative path under the project root")
        )


def _validate_raw_config(
    raw: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    model_registry: FrozenModelRegistry | None,
) -> None:
    _validate_known_keys(
        "$",
        raw,
        {
            "schema_version",
            "name",
            "data",
            "indicators",
            "labels",
            "split",
            "model",
            "signals",
            "portfolio",
            "report",
            "output_dir",
        },
        issues,
    )

    _require_int("schema_version", raw, issues, positive=True)
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        issues.append(
            ConfigValidationIssue(
                "schema_version",
                f"must be {CONFIG_SCHEMA_VERSION}",
            )
        )
    if _require_str("name", raw, issues):
        _validate_experiment_name(raw["name"], issues)
    _optional_str("output_dir", raw, issues)

    data = _section(raw, "data", set(DataConfig.__dataclass_fields__), issues)
    indicators = _section(raw, "indicators", set(IndicatorConfig.__dataclass_fields__), issues)
    labels = _section(raw, "labels", set(LabelConfig.__dataclass_fields__), issues)
    split = _section(raw, "split", set(SplitConfig.__dataclass_fields__), issues)
    model = _section(raw, "model", set(ModelConfig.__dataclass_fields__), issues)
    signals = _section(raw, "signals", set(SignalConfig.__dataclass_fields__), issues)
    portfolio = _section(
        raw,
        "portfolio",
        set(PortfolioConfig.__dataclass_fields__) | {"size", "size_type"},
        issues,
    )
    report = _section(raw, "report", set(ReportConfig.__dataclass_fields__), issues)

    _validate_data(data, issues)
    _validate_indicators(indicators, issues)
    _validate_labels(labels, issues)
    _validate_split(split, issues)
    _validate_label_split_compatibility(labels, split, issues)
    _validate_model(model, issues, model_registry=model_registry)
    _validate_signals(signals, issues)
    _validate_portfolio(portfolio, issues)
    _validate_report(report, issues)


def _validate_label_split_compatibility(
    labels: dict[str, Any],
    split: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    split_kind = split.get("kind", SplitConfig.kind)
    generator = labels.get("generator", {})
    if not isinstance(generator, dict):
        return
    label_kind = generator.get("kind", "fixlb")
    if split_kind != "purged_kfold":
        issues.append(
            ConfigValidationIssue(
                "split.kind",
                f"{label_kind} look-ahead labels require purged_kfold validation",
            )
        )
        return
    if label_kind in {"trendlb", "pivotlb"}:
        issues.append(
            ConfigValidationIssue(
                "labels.generator.kind",
                "purged_kfold requires exact evaluation-time evidence; only fixlb is supported until confirmation-time oracles are configured",
            )
        )


def _validate_data(data: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    source = data.get("source", "synthetic")
    if not _optional_str("data.source", data, issues):
        return
    source = str(source)
    if source not in DATA_SOURCES:
        issues.append(
            ConfigValidationIssue("data.source", f"must be one of {sorted(DATA_SOURCES)}")
        )

    if "symbols" in data:
        _require_str_list("data.symbols", data["symbols"], issues, non_empty=True)
    if source in REMOTE_DATA_SOURCES and "symbols" not in data:
        issues.append(ConfigValidationIssue("data.symbols", "is required for remote data sources"))

    _optional_str("data.start", data, issues, allow_none=True)
    _optional_str("data.end", data, issues, allow_none=True)
    _optional_str("data.timeframe", data, issues)
    _optional_str("data.path", data, issues, allow_none=True)
    _optional_int("data.seed", data, issues)
    _optional_int("data.rows", data, issues, positive=True)

    if source == "csv" and not data.get("path"):
        issues.append(ConfigValidationIssue("data.path", "is required for csv source"))
    if source in REMOTE_DATA_SOURCES:
        for key in ("start", "end", "timeframe"):
            if not data.get(key):
                issues.append(
                    ConfigValidationIssue(f"data.{key}", f"is required for {source} source")
                )

    _optional_enum("data.missing_index", data, MISSING_POLICIES, issues)
    _optional_enum("data.missing_columns", data, MISSING_POLICIES, issues)
    _optional_str_bool_none("data.tz_localize", data, issues)
    _optional_str_bool_none("data.tz_convert", data, issues)
    _optional_bool("data.skip_on_error", data, issues)
    _optional_bool("data.silence_warnings", data, issues)
    _validate_feature_map(data.get("feature_map", {}), issues)
    _validate_quality_policy(data.get("quality", {}), issues)
    _validate_passthrough("data.wrapper_kwargs", data.get("wrapper_kwargs", {}), issues)
    _validate_passthrough("data.provider_kwargs", data.get("provider_kwargs", {}), issues)
    _validate_passthrough("data.execution_kwargs", data.get("execution_kwargs", {}), issues)

    if source in {"synthetic", "csv"}:
        for key in ("wrapper_kwargs", "provider_kwargs", "execution_kwargs"):
            if data.get(key):
                issues.append(
                    ConfigValidationIssue(f"data.{key}", f"is not supported for {source} source")
                )
    if data.get("skip_on_error") and "skipped_symbols" not in _quality_degradations(data):
        issues.append(
            ConfigValidationIssue(
                "data.skip_on_error",
                "requires data.quality.allowed_degradations to include 'skipped_symbols'",
            )
        )


def _validate_feature_map(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "data.feature_map"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    for key, item in value.items():
        child_path = f"{path}.{key}"
        if key not in OHLCV_FEATURE_MAP_KEYS:
            issues.append(
                ConfigValidationIssue(
                    child_path, f"must be one of {sorted(OHLCV_FEATURE_MAP_KEYS)}"
                )
            )
            continue
        if not isinstance(item, str) or not item:
            issues.append(ConfigValidationIssue(child_path, "must be a non-empty string"))


def _validate_quality_policy(value: Any, issues: list[ConfigValidationIssue]) -> None:
    path = "data.quality"
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_known_keys(path, value, set(DataQualityConfig.__dataclass_fields__), issues)
    if "allowed_degradations" in value:
        degradations = value["allowed_degradations"]
        if not isinstance(degradations, list) or not all(
            isinstance(item, str) for item in degradations
        ):
            issues.append(
                ConfigValidationIssue(
                    "data.quality.allowed_degradations",
                    "must be a list of strings",
                )
            )
            return
        for index, degradation in enumerate(degradations):
            if degradation not in DATA_QUALITY_DEGRADATIONS:
                issues.append(
                    ConfigValidationIssue(
                        f"data.quality.allowed_degradations[{index}]",
                        f"must be one of {sorted(DATA_QUALITY_DEGRADATIONS)}",
                    )
                )


def _quality_degradations(data: dict[str, Any]) -> set[str]:
    quality = data.get("quality", {})
    if not isinstance(quality, dict):
        return set()
    degradations = quality.get("allowed_degradations", [])
    if not isinstance(degradations, list):
        return set()
    return {str(item) for item in degradations}


def _validate_indicators(indicators: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_enum(
        "indicators.invalid_value_policy",
        indicators,
        INDICATOR_INVALID_VALUE_POLICIES,
        issues,
    )
    specs = indicators.get("specs")
    if specs is None:
        return
    if not isinstance(specs, list) or not specs:
        issues.append(ConfigValidationIssue("indicators.specs", "must be a non-empty list"))
        return

    seen_ids: set[str] = set()
    registry = indicator_registry()
    for index, spec in enumerate(specs):
        path = f"indicators.specs[{index}]"
        if not isinstance(spec, dict):
            issues.append(ConfigValidationIssue(path, "must be a mapping"))
            continue
        _validate_known_keys(
            path,
            spec,
            {"id", "params", "outputs", "model_features", "grid", "param_product"},
            issues,
        )
        _validate_no_inline_indicator_code(path, spec, issues)
        indicator_id = spec.get("id")
        if not isinstance(indicator_id, str) or not indicator_id:
            issues.append(ConfigValidationIssue(f"{path}.id", "must be a non-empty string"))
            continue
        if indicator_id in seen_ids:
            issues.append(
                ConfigValidationIssue(f"{path}.id", "duplicates another indicator spec id")
            )
        seen_ids.add(indicator_id)
        definition = registry.get(indicator_id)
        if definition is None:
            issues.append(ConfigValidationIssue(f"{path}.id", "is not a registered indicator id"))
            continue
        if not definition.bar_aligned:
            issues.append(
                ConfigValidationIssue(
                    f"{path}.id",
                    "must reference a bar-aligned indicator definition in schema v1",
                )
            )
        _validate_indicator_params(path, spec.get("params", {}), definition, issues)
        _validate_indicator_outputs(path, spec.get("outputs"), definition, issues)
        _validate_indicator_model_features(path, spec.get("model_features"), definition, issues)
        _validate_indicator_grid(path, spec, issues)


def _validate_no_inline_indicator_code(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key) in INDICATOR_INLINE_CODE_KEYS:
                issues.append(
                    ConfigValidationIssue(child_path, "inline code is not allowed in indicators")
                )
            _validate_no_inline_indicator_code(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_inline_indicator_code(f"{path}[{index}]", item, issues)


def _validate_indicator_params(
    spec_path: str,
    params: Any,
    definition: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    path = f"{spec_path}.params"
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_json_like(path, params, issues)
    for param_name in definition.param_names:
        if param_name not in params and param_name not in definition.default_params:
            issues.append(ConfigValidationIssue(f"{path}.{param_name}", "is required"))
    for key, value in params.items():
        child_path = f"{path}.{key}"
        if key not in definition.param_names:
            issues.append(ConfigValidationIssue(child_path, "is not supported by this indicator"))
            continue
        if isinstance(value, list) and not value:
            issues.append(ConfigValidationIssue(child_path, "must not be empty"))
            continue
        values = value if isinstance(value, list) else [value]
        if key == "window":
            for value_index, item in enumerate(values):
                item_path = (
                    child_path if not isinstance(value, list) else f"{child_path}[{value_index}]"
                )
                _validate_int(item_path, item, issues, positive=True)
        if key in definition.allowed_param_values:
            allowed = definition.allowed_param_values[key]
            for value_index, item in enumerate(values):
                item_path = (
                    child_path if not isinstance(value, list) else f"{child_path}[{value_index}]"
                )
                if item not in allowed:
                    issues.append(
                        ConfigValidationIssue(item_path, f"must be one of {sorted(allowed)}")
                    )


def _validate_indicator_outputs(
    spec_path: str,
    outputs: Any,
    definition: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if outputs is None:
        return
    path = f"{spec_path}.outputs"
    if not _require_str_list(path, outputs, issues, non_empty=True):
        return
    for index, output in enumerate(outputs):
        if output not in definition.output_names:
            issues.append(
                ConfigValidationIssue(
                    f"{path}[{index}]",
                    f"must be one of {sorted(definition.output_names)}",
                )
            )


def _validate_indicator_model_features(
    spec_path: str,
    model_features: Any,
    definition: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    if model_features is None:
        return
    path = f"{spec_path}.model_features"
    if not isinstance(model_features, list) or not model_features:
        issues.append(ConfigValidationIssue(path, "must be a non-empty list"))
        return
    for index, feature in enumerate(model_features):
        feature_path = f"{path}[{index}]"
        if not isinstance(feature, dict):
            issues.append(ConfigValidationIssue(feature_path, "must be a mapping"))
            continue
        _validate_known_keys(feature_path, feature, {"output", "transform"}, issues)
        output = feature.get("output")
        if not isinstance(output, str) or not output:
            issues.append(
                ConfigValidationIssue(f"{feature_path}.output", "must be a non-empty string")
            )
        elif output not in definition.output_names:
            issues.append(
                ConfigValidationIssue(
                    f"{feature_path}.output",
                    f"must be one of {sorted(definition.output_names)}",
                )
            )
        transform = feature.get("transform", "identity")
        if not isinstance(transform, str) or not transform:
            issues.append(ConfigValidationIssue(f"{feature_path}.transform", "must be a string"))
        elif transform not in definition.supported_transforms:
            issues.append(
                ConfigValidationIssue(
                    f"{feature_path}.transform",
                    f"must be one of {sorted(definition.supported_transforms)}",
                )
            )


def _validate_indicator_grid(
    spec_path: str,
    spec: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    _optional_enum(f"{spec_path}.grid", spec, INDICATOR_GRIDS, issues)
    _optional_bool(f"{spec_path}.param_product", spec, issues)
    grid = spec.get("grid", "zipped")
    param_product = spec.get("param_product", False)
    if grid == "product" and param_product is not True:
        issues.append(
            ConfigValidationIssue(
                f"{spec_path}.param_product",
                "must be true when grid is 'product'",
            )
        )
    if grid == "zipped" and param_product is True:
        issues.append(
            ConfigValidationIssue(
                f"{spec_path}.grid",
                "must be 'product' when param_product is true",
            )
        )
    if grid != "zipped":
        return
    params = spec.get("params", {})
    if not isinstance(params, dict):
        return
    list_lengths = {
        len(value) for value in params.values() if isinstance(value, list) and len(value) > 1
    }
    if len(list_lengths) > 1:
        issues.append(
            ConfigValidationIssue(
                f"{spec_path}.params",
                "zipped parameter lists must have matching lengths",
            )
        )


def _validate_labels(labels: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    generator = labels.get("generator", {})
    target = labels.get("target", {})
    if not isinstance(generator, dict):
        issues.append(ConfigValidationIssue("labels.generator", "must be a mapping"))
        return
    if not isinstance(target, dict):
        issues.append(ConfigValidationIssue("labels.target", "must be a mapping"))
        return

    _validate_known_keys("labels.generator", generator, {"kind", "params"}, issues)
    _validate_known_keys(
        "labels.target",
        target,
        {"role", "source_output", "select", "transform"},
        issues,
    )
    if not _optional_enum("labels.generator.kind", generator, LABEL_KINDS, issues):
        return

    kind = str(generator.get("kind", "fixlb"))
    params = generator.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue("labels.generator.params", "must be a mapping"))
        return
    _validate_label_generator_params(kind, params, issues)
    effective_params = {**_default_label_generator_params(kind), **params}
    _validate_label_target(kind, effective_params, target, issues)


def _validate_label_generator_params(
    kind: str,
    params: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    if kind == "fixlb":
        _validate_known_keys("labels.generator.params", params, {"n"}, issues)
        if "n" in params:
            _validate_int_or_int_list(
                "labels.generator.params.n", params["n"], issues, positive=True
            )
        return

    if kind == "trendlb":
        _validate_known_keys(
            "labels.generator.params",
            params,
            {"up_th", "down_th", "mode"},
            issues,
        )
        _optional_number("labels.generator.params.up_th", params, issues, positive=True)
        _optional_number("labels.generator.params.down_th", params, issues, positive=True)
        _optional_enum("labels.generator.params.mode", params, TRENDLB_MODES, issues)
        return

    if kind == "pivotlb":
        _validate_known_keys("labels.generator.params", params, {"up_th", "down_th"}, issues)
        _optional_number("labels.generator.params.up_th", params, issues, positive=True)
        _optional_number("labels.generator.params.down_th", params, issues, positive=True)


def _validate_label_target(
    kind: str,
    params: dict[str, Any],
    target: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    _optional_enum("labels.target.role", target, LABEL_TARGET_ROLES, issues)
    source_output = target.get("source_output", "labels")
    if "source_output" in target and not isinstance(source_output, str):
        issues.append(ConfigValidationIssue("labels.target.source_output", "must be a string"))
    elif source_output != "labels":
        issues.append(ConfigValidationIssue("labels.target.source_output", "must be 'labels'"))

    select = target.get("select", {})
    if not isinstance(select, dict):
        issues.append(ConfigValidationIssue("labels.target.select", "must be a mapping"))
        return
    _validate_known_keys("labels.target.select", select, {"params"}, issues)
    select_params = select.get("params", {})
    if not isinstance(select_params, dict):
        issues.append(ConfigValidationIssue("labels.target.select.params", "must be a mapping"))
        return
    _validate_target_selection(kind, params, select_params, issues)

    transform = target.get("transform", {})
    if not isinstance(transform, dict):
        issues.append(ConfigValidationIssue("labels.target.transform", "must be a mapping"))
        return
    _validate_known_keys(
        "labels.target.transform", transform, {"name", "version", "params"}, issues
    )
    _optional_enum("labels.target.transform.name", transform, LABEL_TARGET_TRANSFORMS, issues)
    _optional_int("labels.target.transform.version", transform, issues, positive=True)
    transform_name = str(
        transform.get("name")
        or _default_label_transform_name(LabelGeneratorConfig(kind=kind, params=params))
    )
    transform_params = transform.get("params", {})
    if not isinstance(transform_params, dict):
        issues.append(ConfigValidationIssue("labels.target.transform.params", "must be a mapping"))
        return
    _validate_label_transform(kind, params, transform_name, transform_params, issues)


def _validate_target_selection(
    kind: str,
    params: dict[str, Any],
    select_params: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    parameter_keys = {"n"} if kind == "fixlb" else set(params)
    _validate_known_keys("labels.target.select.params", select_params, parameter_keys, issues)
    for key, value in params.items():
        if isinstance(value, list) and len(value) > 1 and key not in select_params:
            issues.append(
                ConfigValidationIssue(
                    f"labels.target.select.params.{key}",
                    "is required when generator parameter has multiple values",
                )
            )
    for key, selected in select_params.items():
        values = params.get(key)
        if isinstance(values, list):
            if selected in values:
                continue
            issues.append(
                ConfigValidationIssue(
                    f"labels.target.select.params.{key}",
                    f"must be one of {values}",
                )
            )
            continue
        if values is not None and selected != values:
            issues.append(
                ConfigValidationIssue(
                    f"labels.target.select.params.{key}",
                    f"must be {values!r}",
                )
            )


def _validate_label_transform(
    kind: str,
    params: dict[str, Any],
    transform_name: str,
    transform_params: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    mode = params.get("mode", "binary")
    if kind == "fixlb" and transform_name != "threshold_future_return":
        issues.append(
            ConfigValidationIssue(
                "labels.target.transform.name",
                "must be 'threshold_future_return' for fixlb",
            )
        )
    if kind == "trendlb" and mode == "binary" and transform_name != "identity_binary":
        issues.append(
            ConfigValidationIssue(
                "labels.target.transform.name",
                "must be 'identity_binary' for binary trendlb",
            )
        )
    if kind == "trendlb" and mode != "binary" and transform_name != "continuous_identity":
        issues.append(
            ConfigValidationIssue(
                "labels.target.transform.name",
                "must be 'continuous_identity' for continuous trendlb modes",
            )
        )
    if kind == "pivotlb" and transform_name != "positive_event":
        issues.append(
            ConfigValidationIssue(
                "labels.target.transform.name",
                "must be 'positive_event' for pivotlb",
            )
        )

    if transform_name == "threshold_future_return":
        _validate_known_keys(
            "labels.target.transform.params", transform_params, {"threshold"}, issues
        )
        _optional_number("labels.target.transform.params.threshold", transform_params, issues)
    elif transform_name in {"identity_binary", "positive_event"}:
        _validate_known_keys(
            "labels.target.transform.params", transform_params, {"positive_value"}, issues
        )
        _optional_int("labels.target.transform.params.positive_value", transform_params, issues)
        positive_value = transform_params.get("positive_value", 1)
        if kind == "pivotlb" and positive_value not in {-1, 1}:
            issues.append(
                ConfigValidationIssue(
                    "labels.target.transform.params.positive_value",
                    "must be -1 or 1 for pivotlb",
                )
            )
    elif transform_name == "continuous_identity":
        _validate_known_keys("labels.target.transform.params", transform_params, set(), issues)


def _validate_split(split: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    kind = split.get("kind", SplitConfig.kind)
    if not _optional_enum("split.kind", split, SPLIT_KINDS, issues):
        return
    kind = str(kind)
    _validate_purged_kfold_split(split, kind, issues)


def _validate_purged_kfold_split(
    split: dict[str, Any],
    kind: str,
    issues: list[ConfigValidationIssue],
) -> None:
    _optional_int("split.n_folds", split, issues, minimum=2)
    _optional_int("split.n_test_folds", split, issues, positive=True)
    _optional_timedelta("split.purge_td", split, issues, minimum=pd.Timedelta(0))
    _optional_timedelta("split.embargo_td", split, issues, minimum=pd.Timedelta(0))
    _optional_int("split.max_splits", split, issues, positive=True)
    _optional_int("split.max_estimated_output_cells", split, issues, positive=True)
    _optional_int("split.max_public_artifact_bytes", split, issues, positive=True)

    if kind != "purged_kfold":
        return

    n_folds_value = split.get("n_folds", SplitConfig.n_folds)
    n_test_folds_value = split.get("n_test_folds", SplitConfig.n_test_folds)
    max_splits_value = split.get("max_splits", SplitConfig.max_splits)
    if not (_is_int(n_folds_value) and _is_int(n_test_folds_value) and _is_int(max_splits_value)):
        return

    n_folds = int(n_folds_value)
    n_test_folds = int(n_test_folds_value)
    if n_test_folds != 1:
        issues.append(
            ConfigValidationIssue(
                "split.n_test_folds",
                "must be 1 until overlapping CPCV aggregation is supported",
            )
        )
        return
    if n_test_folds >= n_folds:
        issues.append(
            ConfigValidationIssue(
                "split.n_test_folds",
                "must be less than split.n_folds for purged_kfold",
            )
        )
        return
    max_splits = int(max_splits_value)
    split_count = math.comb(n_folds, n_test_folds)
    if split_count > max_splits:
        issues.append(
            ConfigValidationIssue(
                "split.max_splits",
                f"must be at least {split_count} for purged_kfold",
            )
        )


def _validate_model(
    model: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    model_registry: FrozenModelRegistry | None,
) -> None:
    _optional_str("model.plugin_id", model, issues, allow_none=True)
    _optional_int("model.min_train_samples", model, issues, positive=True)
    params = model.get("params", {})
    if not isinstance(params, dict):
        issues.append(ConfigValidationIssue("model.params", "must be a mapping"))
    else:
        _validate_json_like("model.params", params, issues)
        _validate_no_inline_secrets("model.params", params, issues)
    _validate_no_denied_model_keys("model", model, issues)
    if model_registry is None:
        return
    plugin_id = model.get("plugin_id")
    if not isinstance(plugin_id, str) or not plugin_id:
        issues.append(ConfigValidationIssue("model.plugin_id", "is required"))
        return
    if plugin_id not in model_registry:
        issues.append(
            ConfigValidationIssue("model.plugin_id", "unknown registered model plugin id")
        )
        return
    definition = model_registry.get(plugin_id)
    if definition.validate_params is not None and isinstance(params, dict):
        for param_path, message in definition.validate_params(params).items():
            child_path = f"model.params.{param_path}" if param_path else "model.params"
            issues.append(ConfigValidationIssue(child_path, message))


def _assert_model_config_registered(
    model: ModelConfig,
    model_registry: FrozenModelRegistry,
) -> None:
    issues: list[ConfigValidationIssue] = []
    _validate_model(
        to_builtin(asdict(model)),
        issues,
        model_registry=model_registry,
    )
    if issues:
        raise ConfigValidationError(issues)


def _validate_signals(signals: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_enum("signals.policy", signals, SIGNAL_POLICIES, issues)
    _optional_enum("signals.execution_timing", signals, SIGNAL_EXECUTION_TIMINGS, issues)
    long_entry_threshold = signals.get("long_entry_threshold", 0.55)
    long_exit_threshold = signals.get("long_exit_threshold", 0.50)
    entry_ok = _optional_number(
        "signals.long_entry_threshold",
        signals,
        issues,
        minimum=0,
        maximum=1,
    )
    exit_ok = _optional_number(
        "signals.long_exit_threshold",
        signals,
        issues,
        minimum=0,
        maximum=1,
    )
    if entry_ok and exit_ok and float(long_exit_threshold) >= float(long_entry_threshold):
        issues.append(
            ConfigValidationIssue(
                "signals.long_exit_threshold",
                "must be less than signals.long_entry_threshold",
            )
        )


def _validate_portfolio(portfolio: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("portfolio.init_cash", portfolio, issues, positive=True)
    _optional_number("portfolio.fees", portfolio, issues, minimum=0)
    _optional_number("portfolio.slippage", portfolio, issues, minimum=0)
    if "entry_budget" not in portfolio:
        issues.append(ConfigValidationIssue("portfolio.entry_budget", "is required"))
    else:
        _optional_number("portfolio.entry_budget", portfolio, issues, positive=True, maximum=1)
    if "size" in portfolio:
        issues.append(
            ConfigValidationIssue(
                "portfolio.size",
                "was removed; use portfolio.entry_budget for v1 signal entry sizing",
            )
        )
    if "size_type" in portfolio and not isinstance(portfolio["size_type"], str):
        issues.append(ConfigValidationIssue("portfolio.size_type", "must be a string"))
    elif "size_type" in portfolio:
        if portfolio["size_type"] in PORTFOLIO_TARGET_SIZE_TYPES:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "target allocation sizing is deferred; baseline signal simulation uses portfolio.entry_budget",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.size_type",
                    "was removed; baseline signal simulation resolves valuepercent sizing internally",
                )
            )
    direction = portfolio.get("direction", "longonly")
    if "direction" in portfolio and not isinstance(direction, str):
        issues.append(ConfigValidationIssue("portfolio.direction", "must be a string"))
    elif direction != "longonly":
        if direction in {"both", "shortonly"}:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    "v1 positive_class_probability signal contract is long-only; use longonly",
                )
            )
        else:
            issues.append(
                ConfigValidationIssue(
                    "portfolio.direction",
                    f"must be one of {sorted(PORTFOLIO_DIRECTIONS)}",
                )
            )


def _validate_report(report: dict[str, Any], issues: list[ConfigValidationIssue]) -> None:
    _optional_number("report.min_oos_sharpe", report, issues)
    _optional_number("report.max_oos_drawdown", report, issues, minimum=0, maximum=1)
    _optional_int("report.min_oos_trades", report, issues, minimum=0)
    if "freq" in report:
        _require_timedelta_str("report.freq", report, issues)
    if "year_freq" in report:
        _require_timedelta_str("report.year_freq", report, issues)


def _require_timedelta_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> None:
    key = path.rsplit(".", 1)[-1]
    if not _require_str(path, mapping, issues):
        return
    value = _parse_timedelta(
        path,
        mapping[key],
        issues,
        message="must be a Timedelta-compatible string",
    )
    if value is None:
        return
    if value <= pd.Timedelta(0):
        issues.append(ConfigValidationIssue(path, "must be positive"))


def _validate_experiment_name(value: str, issues: list[ConfigValidationIssue]) -> None:
    if not EXPERIMENT_NAME_RE.fullmatch(value) or value in {".", ".."}:
        issues.append(
            ConfigValidationIssue(
                "name",
                "must contain only letters, numbers, dots, underscores, and hyphens",
            )
        )


def _section(
    raw: dict[str, Any],
    name: str,
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(name, "must be a mapping"))
        return {}
    _validate_known_keys(name, value, allowed, issues)
    return value


def _validate_known_keys(
    path: str,
    value: dict[str, Any],
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> None:
    for key in sorted(set(value) - allowed):
        child_path = key if path == "$" else f"{path}.{key}"
        issues.append(ConfigValidationIssue(child_path, "unknown field"))


def _validate_passthrough(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(ConfigValidationIssue(path, "must be a mapping"))
        return
    _validate_json_like(path, value, issues)
    _validate_no_inline_secrets(path, value, issues)
    _validate_no_denied_passthrough_keys(path, value, issues)


def _validate_no_denied_passthrough_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    _validate_no_denied_keys(
        path,
        value,
        DENIED_PASSTHROUGH_KEYS,
        "is not allowed in passthrough config",
        issues,
    )


def _validate_no_denied_model_keys(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> None:
    _validate_no_denied_keys(
        path,
        value,
        MODEL_DENIED_KEYS,
        "is not allowed in model config; register trusted plugin code before validation",
        issues,
    )


def _validate_no_denied_keys(
    path: str,
    value: Any,
    denied_keys: set[str],
    message: str,
    issues: list[ConfigValidationIssue],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in denied_keys:
                issues.append(ConfigValidationIssue(child_path, message))
            _validate_no_denied_keys(child_path, item, denied_keys, message, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_denied_keys(f"{path}[{index}]", item, denied_keys, message, issues)


def _validate_json_like(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if _is_number(value):
        try:
            number = float(value)
        except OverflowError:
            issues.append(ConfigValidationIssue(path, "must be finite"))
            return
        if not math.isfinite(number):
            issues.append(ConfigValidationIssue(path, "must be finite"))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_like(f"{path}[{index}]", item, issues)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                issues.append(
                    ConfigValidationIssue(f"{path}.{key}", "mapping keys must be strings")
                )
                continue
            _validate_json_like(f"{path}.{key}", item, issues)
        return
    issues.append(ConfigValidationIssue(path, "must be JSON-serializable"))


def _validate_no_inline_secrets(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if _is_secret_ref(value):
        env_name = value["env"]
        if not isinstance(env_name, str) or not env_name.strip():
            issues.append(
                ConfigValidationIssue(
                    path, "env secret reference must name an environment variable"
                )
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_RE.search(str(key)) and not _is_secret_ref(item):
                issues.append(
                    ConfigValidationIssue(
                        child_path,
                        "inline credentials are not allowed; use an env secret reference",
                    )
                )
            _validate_no_inline_secrets(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_inline_secrets(f"{path}[{index}]", item, issues)
        return
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        issues.append(
            ConfigValidationIssue(path, "secret-like values must be expressed as env references")
        )


def _require_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        issues.append(ConfigValidationIssue(path, "is required"))
        return False
    return _optional_str(path, mapping, issues, allow_none=allow_none)


def _optional_str(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    return _validate_str(path, mapping[key], issues, allow_none=allow_none)


def _validate_str(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    allow_none: bool = False,
) -> bool:
    if value is None and allow_none:
        return True
    if not isinstance(value, str) or not value:
        issues.append(ConfigValidationIssue(path, "must be a non-empty string"))
        return False
    return True


def _optional_str_bool_none(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    if mapping[key] is None or isinstance(mapping[key], str | bool):
        return True
    issues.append(ConfigValidationIssue(path, "must be a string, boolean, or null"))
    return False


def _optional_bool(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    if isinstance(mapping[key], bool):
        return True
    issues.append(ConfigValidationIssue(path, "must be a boolean"))
    return False


def _require_int(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        issues.append(ConfigValidationIssue(path, "is required"))
        return False
    return _optional_int(path, mapping, issues, positive=positive, minimum=minimum)


def _optional_int(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    return _validate_int(path, mapping[key], issues, positive=positive, minimum=minimum)


def _validate_int(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: int | None = None,
) -> bool:
    if not _is_int(value):
        issues.append(ConfigValidationIssue(path, "must be an integer"))
        return False
    if positive and int(value) <= 0:
        issues.append(ConfigValidationIssue(path, "must be positive"))
        return False
    if minimum is not None and int(value) < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
        return False
    return True


def _validate_int_or_int_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
) -> bool:
    if isinstance(value, list):
        if not value:
            issues.append(ConfigValidationIssue(path, "must not be empty"))
            return False
        ok = True
        for index, item in enumerate(value):
            ok = _validate_int(f"{path}[{index}]", item, issues, positive=positive) and ok
        return ok
    return _validate_int(path, value, issues, positive=positive)


def _optional_number(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if not _is_number(value):
        issues.append(ConfigValidationIssue(path, "must be a number"))
        return False
    try:
        number = float(value)
    except OverflowError:
        issues.append(ConfigValidationIssue(path, "must be finite"))
        return False
    if not math.isfinite(number):
        issues.append(ConfigValidationIssue(path, "must be finite"))
        return False
    if positive and number <= 0:
        issues.append(ConfigValidationIssue(path, "must be positive"))
        return False
    if minimum is not None and number < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
        return False
    if maximum is not None and number > maximum:
        issues.append(ConfigValidationIssue(path, f"must be at most {maximum}"))
        return False
    return True


def _optional_timedelta(
    path: str,
    mapping: dict[str, Any],
    issues: list[ConfigValidationIssue],
    *,
    minimum: pd.Timedelta | None = None,
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if isinstance(value, bool):
        issues.append(ConfigValidationIssue(path, "must be a timedelta-compatible value"))
        return False
    timedelta = _parse_timedelta(
        path,
        value,
        issues,
        message="must be a timedelta-compatible value",
    )
    if timedelta is None:
        return False
    if minimum is not None and timedelta < minimum:
        issues.append(ConfigValidationIssue(path, f"must be at least {minimum}"))
        return False
    return True


def _parse_timedelta(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    message: str,
) -> pd.Timedelta | None:
    try:
        return pd.Timedelta(value)
    except (TypeError, ValueError):
        issues.append(ConfigValidationIssue(path, message))
        return None


def _optional_enum(
    path: str,
    mapping: dict[str, Any],
    allowed: set[str],
    issues: list[ConfigValidationIssue],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    if key not in mapping:
        return True
    value = mapping[key]
    if not isinstance(value, str):
        issues.append(ConfigValidationIssue(path, "must be a string"))
        return False
    if value not in allowed:
        issues.append(ConfigValidationIssue(path, f"must be one of {sorted(allowed)}"))
        return False
    return True


def _require_str_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    non_empty: bool = False,
) -> bool:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        issues.append(ConfigValidationIssue(path, "must be a list of non-empty strings"))
        return False
    if non_empty and not value:
        issues.append(ConfigValidationIssue(path, "must not be empty"))
        return False
    return True


def _require_int_list(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
    *,
    positive: bool = False,
) -> bool:
    if not isinstance(value, list) or not all(_is_int(item) for item in value):
        issues.append(ConfigValidationIssue(path, "must be a list of integers"))
        return False
    if positive and any(int(item) <= 0 for item in value):
        issues.append(ConfigValidationIssue(path, "must contain only positive integers"))
        return False
    return True


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_secret_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"env"}


def resolve_secret_refs(value: Any, path: str = "$") -> tuple[Any, list[str]]:
    issues: list[ConfigValidationIssue] = []
    resolved, secrets = _resolve_secret_refs(path, value, issues)
    if issues:
        raise ConfigValidationError(issues)
    return resolved, secrets


def _resolve_secret_refs(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> tuple[Any, list[str]]:
    if _is_secret_ref(value):
        env_name = value["env"]
        secret = os.environ.get(env_name, "")
        if not secret:
            issues.append(
                ConfigValidationIssue(path, f"environment variable {env_name!r} is not set")
            )
            return None, []
        return secret, [secret]
    if isinstance(value, dict):
        resolved: dict[str, Any] = {}
        secrets: list[str] = []
        for key, item in value.items():
            resolved_item, item_secrets = _resolve_secret_refs(f"{path}.{key}", item, issues)
            resolved[key] = resolved_item
            secrets.extend(item_secrets)
        return resolved, secrets
    if isinstance(value, list):
        resolved_list = []
        secrets = []
        for index, item in enumerate(value):
            resolved_item, item_secrets = _resolve_secret_refs(f"{path}[{index}]", item, issues)
            resolved_list.append(resolved_item)
            secrets.extend(item_secrets)
        return resolved_list, secrets
    return value, []


def redact_config(value: Any) -> Any:
    if _is_secret_ref(value):
        return {"env": "<redacted>"}
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                redacted[key] = {"env": "<redacted>"} if _is_secret_ref(item) else "<redacted>"
            else:
                redacted[key] = redact_config(item)
        return redacted
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        return "<redacted>"
    return value


def redact_text(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return SECRET_VALUE_RE.sub("<redacted>", redacted)


def known_config_secret_values(value: Any) -> tuple[str, ...]:
    secrets: list[str] = []
    _collect_known_config_secret_values(value, secrets)
    return tuple(secrets)


def _collect_known_config_secret_values(value: Any, secrets: list[str]) -> None:
    if isinstance(value, dict) and set(value) == {"env"}:
        secret = os.environ.get(str(value["env"]), "")
        if secret:
            secrets.append(secret)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_known_config_secret_values(item, secrets)
        return
    if isinstance(value, list):
        for item in value:
            _collect_known_config_secret_values(item, secrets)


def to_builtin(value: Any) -> Any:
    if isinstance(value, ResolvedExperimentConfig):
        return to_builtin(asdict(value.config))
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_builtin(v) for v in value]
    return value
