from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

import pandas as pd
from pydantic import ConfigDict, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.configuration.field_types import (
    NonNegativeRate,
    PositiveCash,
    StrictFloat,
    UnitInterval,
)

CONFIG_SCHEMA_VERSION = 8
EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
OHLCV_ARRAYS = ("Open", "High", "Low", "Close", "Volume")
# This is intentionally a shortcut catalog, not a universal feature catalog.
# Full VBT feature names are source-specific and discovered from native_data.features.
DATA_ARRAY_SHORTCUTS = {"OHLCV": OHLCV_ARRAYS}

PORTFOLIO_TARGET_SIZE_TYPES = {
    "targetamount",
    "targetvalue",
    "targetpercent",
    "targetpercent100",
}
PORTFOLIO_DIRECTIONS = {"longonly", "shortonly", "both"}
SIGNAL_POLICIES = {"long_only_hysteresis"}
SIGNAL_EXECUTION_TIMINGS = {"next_open", "same_close"}
MISSING_POLICIES = {"nan", "drop", "raise"}
DATA_QUALITY_DEGRADATIONS = {
    "duplicate_index",
    "missing_rows",
    "non_monotonic_index",
    "skipped_symbols",
}
FORWARD_OPTIMIZATION_REQUIRED_MESSAGE = (
    "is required; fixed/non-optimized strategy runs are removed from the forward "
    "run contract; use optimization.search and optimization.split"
)
OPTIMIZATION_SEARCH_POLICIES = {"grid", "random"}


@dataclass(frozen=True)
class ConfigValidationIssue:
    path: str
    message: str


class ConfigValidationError(ValueError):
    def __init__(self, issues: list[ConfigValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"Invalid run config: {details}")


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


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunSplitConfig:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    max_splits: int = 100
    max_estimated_output_cells: int = 25_000_000
    max_public_artifact_bytes: int = 10_000_000

    @model_validator(mode="after")
    def _no_set_labels(self):
        if "set_labels" in self.params:
            raise ValueError(
                "set roles are owned by Aegis and assigned positionally "
                "(set 0 selection, set 1 held_out); set_labels is not configurable"
            )
        return self


@dataclass(frozen=True)
class SignalConfig:
    policy: str = "long_only_hysteresis"
    long_entry_threshold: float = 0.55
    long_exit_threshold: float = 0.50
    execution_timing: str = "next_open"


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class PortfolioConfig:
    init_cash: PositiveCash = 10_000.0
    fees: NonNegativeRate = 0.001
    slippage: NonNegativeRate = 0.0005
    net_cap: NonNegativeRate = 1.0
    # Short financing carry: flat annual rates. Effective net carry = borrow - rebate,
    # charged only on short legs (see ADR-0008). The non-zero borrow default means carry
    # is ON by default; a long-only book has no short legs and is unaffected.
    short_borrow_rate: NonNegativeRate = 0.005
    short_rebate_rate: NonNegativeRate = 0.0
    # No schema default — required. Keyword-only so a required field can sit among
    # defaulted ones — every construction site splats **raw anyway.
    gross_cap: PositiveCash = field(kw_only=True)
    # Required (validation rejects a config missing it); no silent long-only default.
    direction: Literal["longonly", "shortonly", "both"] = field(kw_only=True)

    # Tombstone fields rejected by the coordinator prepass (NOT @model_validator —
    # a validator raising ValueError loses the dotted path and mangles the message).
    REMOVED_FIELDS: ClassVar[dict[str, str]] = {
        "entry_budget": "renamed to portfolio.gross_cap",
        "target_exposure_cap": (
            "was replaced by portfolio.gross_cap (max Σ|wᵢ|) "
            "and portfolio.net_cap (max |Σwᵢ|)"
        ),
        "size": "was removed; use portfolio.gross_cap for exposure sizing",
    }
    _SIZE_TYPE_TOMBSTONES: ClassVar[dict[str, str]] = {
        "target": (
            "target allocation sizing is resolved internally; "
            "size_type is not a config knob"
        ),
        "other": (
            "was removed; the simulator resolves targetpercent sizing internally"
        ),
    }


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ReportConfig:
    min_oos_sharpe: StrictFloat = 0.5
    max_oos_drawdown: UnitInterval = 0.35
    min_oos_trades: int = 5
    freq: str = "1D"
    year_freq: str = "252D"

    @property
    def periods_per_year(self) -> int:
        """Trading periods per year on the metric-annualization calendar.

        ``year_freq / freq`` (252 for the daily defaults) so short-financing carry and the
        Sharpe ratio share one calendar (ADR-0008). Rounded to the nearest whole period.
        """
        return round(pd.Timedelta(self.year_freq) / pd.Timedelta(self.freq))


@dataclass(frozen=True)
class RunSourceRefConfig:
    id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunIndicatorSourceConfig:
    id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingConfig:
    metric: str
    min_weight: float = 0.3
    min_trades: int = 0


OPTIMIZATION_EXECUTE_RESERVED_KEYS = frozenset(
    {
        "random_subset",
        "seed",
        "merge_func",
        "raise_no_results",
        "filter_results",
    }
)


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class OptimizationConfig:
    search: Literal["grid", "random"]
    split: RunSplitConfig
    random_subset: int | None = None
    seed: int | None = None
    execute: dict[str, Any] = field(default_factory=dict)

    @model_validator(mode="after")
    def _random_needs_subset_and_seed(self):
        if self.search == "random":
            if self.random_subset is None:
                raise ValueError(
                    "random_subset is required when optimization.search is 'random'"
                )
            if self.seed is None:
                raise ValueError(
                    "seed is required when optimization.search is 'random' "
                    "so sampled evidence is deterministic"
                )
        if self.search == "grid" and self.random_subset is not None:
            raise ValueError(
                "random_subset is only valid when optimization.search is 'random'"
            )
        return self

    @model_validator(mode="after")
    def _execute_no_reserved_keys(self):
        reserved = sorted(set(self.execute) & OPTIMIZATION_EXECUTE_RESERVED_KEYS)
        if reserved:
            raise ValueError(
                f"reserved keys {reserved} are owned by optimization.search / "
                "Aegis ranking policy and must not appear "
                "under optimization.execute"
            )
        return self


# The representative roles a Lock handle may name, in rank order. These mirror the
# roles evidence emits for every Run (evidence.CANDIDATE_ROLES); the config layer keeps
# its own copy because it must not depend up on the optimization layer.
LOCK_ROLES: tuple[str, ...] = ("best", "median", "worst")
DEFAULT_LOCK_ROLE = "best"


def split_lock_handle(value: str) -> tuple[str, str | None]:
    """Split a scalar ``lock:`` handle ``run_id[:role]`` into ``(run_id, role|None)``.

    Pure syntax: splits on the first ``:`` and reports a missing role as ``None`` (the
    caller defaults it). It does not validate role membership or a non-empty run_id —
    that is the lock validator's job, so malformed handles fail at config validation.
    """
    run_id, separator, role = value.partition(":")
    return run_id, (role if separator else None)


@dataclass(frozen=True)
class Lock:
    """A top-level Run Config reference that reproduces one prior Candidate.

    ``run_id`` + ``candidate_id`` together *are* the ``candidates`` primary key
    ``(run_id, candidate_key)`` — so a Lock needs no separate storage. A locked
    Run takes every Component's parameters from that Candidate rather than
    searching for new ones.

    ``candidate_id`` carries either a representative role keyword (one of
    ``LOCK_ROLES`` — the ergonomic handle, resolved through ``candidate_rankings``)
    or a raw ``candidate_key`` hash (the durable, exact reference). A scalar
    ``lock: run_id[:role]`` lands here with the role keyword (default ``best``).
    """

    run_id: str
    candidate_id: str


@dataclass(frozen=True)
class RunConfig:
    name: str
    strategy: RunSourceRefConfig
    indicators: list[RunIndicatorSourceConfig]
    ranking: RankingConfig
    schema_version: int = CONFIG_SCHEMA_VERSION
    data: DataConfig = field(default_factory=DataConfig)
    # Required (keyword-only so it can sit among defaulted fields): a run must declare its
    # portfolio, which in turn requires an explicit direction — no silently long-only default.
    portfolio: PortfolioConfig = field(kw_only=True)
    report: ReportConfig = field(default_factory=ReportConfig)
    optimization: OptimizationConfig | None = None
    lock: Lock | None = None
    output_dir: str = "runs"


@dataclass(frozen=True)
class ConfigSelectionEvidence:
    source: str
    config_path: str | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "config_path": self.config_path,
        }
