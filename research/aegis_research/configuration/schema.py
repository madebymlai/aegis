from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONFIG_SCHEMA_VERSION = 4
EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
OHLCV_ARRAYS = ("Open", "High", "Low", "Close", "Volume")
# This is intentionally a shortcut catalog, not a universal feature catalog.
# Full VBT feature names are source-specific and discovered from native_data.features.
DATA_ARRAY_SHORTCUTS = {"OHLCV": OHLCV_ARRAYS}

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
LANES = {"run", "train"}
SOURCE_KINDS = {"component", "playbook"}
MODEL_SOURCE_KINDS = {"plugin"}
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
    arrays: list[str] = field(default_factory=lambda: ["OHLCV"])
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
    quality: DataQualityConfig = field(default_factory=DataQualityConfig)
    wrapper_kwargs: dict[str, Any] = field(default_factory=dict)
    provider_kwargs: dict[str, Any] = field(default_factory=dict)
    execution_kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_arrays(self) -> tuple[str, ...]:
        return expand_data_arrays(self.arrays)


def expand_data_arrays(arrays: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    tokens = tuple(arrays)
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for feature in DATA_ARRAY_SHORTCUTS.get(token, (token,)):
            if feature in seen:
                continue
            expanded.append(feature)
            seen.add(feature)
    return tuple(expanded)


def has_data_array_token_shape(value: str) -> bool:
    return bool(value) and value.strip() == value and not any(char in "\t\n\r" for char in value)


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
class LabelerConfig:
    id: str


@dataclass(frozen=True)
class RunSourceRefConfig:
    source: str
    id: str


@dataclass(frozen=True)
class RunIndicatorSourceConfig:
    source: str
    ids: str | list[str]

    def expanded_ids(self, available_ids: tuple[str, ...]) -> tuple[str, ...]:
        return available_ids if self.ids == "all" else tuple(self.ids)


@dataclass(frozen=True)
class RankingConfig:
    metric: str
    direction: str
    rank_by: str = "primary_metric"


@dataclass(frozen=True)
class CandidateGridConfig:
    max_candidates: int = 100_000
    max_estimated_cells: int = 50_000_000
    batch_size: int = 1_000


@dataclass(frozen=True)
class TrainModelConfig:
    source: str
    id: str
    min_train_samples: int = 100
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def plugin_id(self) -> str:
        return self.id


@dataclass(frozen=True)
class StrategyRunLaneConfig:
    name: str
    strategy: RunSourceRefConfig
    indicators: list[RunIndicatorSourceConfig]
    ranking: RankingConfig
    schema_version: int = CONFIG_SCHEMA_VERSION
    lane: str = "run"
    data: DataConfig = field(default_factory=DataConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    candidate_grid: CandidateGridConfig = field(default_factory=CandidateGridConfig)
    output_dir: str = "runs"


@dataclass(frozen=True)
class TrainLaneConfig:
    name: str
    labeler: LabelerConfig
    model: TrainModelConfig
    indicators: list[RunIndicatorSourceConfig]
    schema_version: int = CONFIG_SCHEMA_VERSION
    lane: str = "train"
    data: DataConfig = field(default_factory=DataConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    output_dir: str = "runs"


LaneConfig = StrategyRunLaneConfig | TrainLaneConfig


@dataclass(frozen=True)
class ConfigSelectionEvidence:
    source: str
    config_path: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "config_path": self.config_path,
        }
