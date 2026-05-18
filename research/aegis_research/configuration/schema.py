from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONFIG_SCHEMA_VERSION = 2
EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

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
