from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Literal

import pandas as pd
from pydantic import AfterValidator, ConfigDict, Field, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.configuration.field_types import (
    EXPERIMENT_NAME_RE,  # noqa: F401 — re-exported for config.py
    ComponentIdStr,
    NonNegativeInt,
    NonNegativeRate,
    PositiveCash,
    StrictFloat,
    UnitInterval,
)

CONFIG_SCHEMA_VERSION = 8
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


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class DataQualityConfig:
    allowed_degradations: list[str] = field(default_factory=list)


def _validate_array_token(token: str) -> str:
    """Pydantic item-validator: reject tokens not in shortcuts or malformed."""
    if token in DATA_ARRAY_SHORTCUTS:
        return token
    if not has_data_array_token_shape(token):
        raise ValueError(
            "must be a VBT feature name without surrounding whitespace or control characters"
        )
    return token


ArrayToken = Annotated[str, AfterValidator(_validate_array_token)]


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class DataConfig:
    source: str = "synthetic"
    # No schema default — required. Keyword-only so a required field can sit among
    # defaulted ones — every construction site splats **raw anyway.
    arrays: Annotated[list[ArrayToken], Field(min_length=1)] = field(kw_only=True)
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

    @model_validator(mode="after")
    def _validate_conditional_requireds(self) -> DataConfig:
        """Cross-field conditional requiredness.

        - Remote sources require non-empty symbols.
        - csv source requires a path.
        - skip_on_error requires quality to allow 'skipped_symbols'.
        - Local sources (synthetic, csv) do not support provider/execution kwargs.

        Source whitelisting is NOT here — it's a post-pydantic check in the
        resolution coordinator so programmatic DataConfig construction (which
        uses internal source names like "frame") is not rejected at the model
        level.
        """
        from research.aegis_research.market_data.sources import (
            LOCAL_DATA_SOURCES,
            remote_data_sources,
        )

        supported_remote = remote_data_sources()
        if self.source in supported_remote:
            if not self.symbols:
                raise ValueError(
                    f"symbols is required for {self.source} source"
                )
            for field_name in ("start", "end", "timeframe"):
                if not getattr(self, field_name):
                    raise ValueError(
                        f"{field_name} is required for {self.source} source"
                    )
        if self.source == "csv" and not self.path:
            raise ValueError("path is required for csv source")
        if self.skip_on_error and "skipped_symbols" not in self.quality.allowed_degradations:
            raise ValueError(
                "skip_on_error requires data.quality.allowed_degradations to include 'skipped_symbols'"
            )
        if self.source in LOCAL_DATA_SOURCES:
            for key in ("wrapper_kwargs", "provider_kwargs", "execution_kwargs"):
                if getattr(self, key):
                    raise ValueError(
                        f"{key} is not supported for {self.source} source"
                    )
        return self


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


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunSourceRefConfig:
    id: ComponentIdStr
    params: dict[str, Any] = field(default_factory=dict)


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunIndicatorSourceConfig:
    id: ComponentIdStr
    params: dict[str, Any] = field(default_factory=dict)


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RankingConfig:
    metric: str
    min_weight: UnitInterval = 0.3
    min_trades: NonNegativeInt = 0


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


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
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

    @model_validator(mode="before")
    @classmethod
    def _coerce_handle(cls, data: Any) -> Any:
        """Normalize a scalar ``run_id[:role]`` handle to the mapping shape."""
        if isinstance(data, str):
            run_id, _, role = data.partition(":")
            return {"run_id": run_id, "candidate_id": role or DEFAULT_LOCK_ROLE}
        return data


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunConfig:
    """Whole-tree pydantic dataclass: one ``TypeAdapter(RunConfig).validate_python(raw)``
    validates the entire run config and accumulates all structural errors across sections.

    Top-level prepass (removed-training-field tombstones, portfolio tombstones,
    ``schema_version`` presence check) lives in the resolution coordinator so custom
    messages survive (``@model_validator`` loses dotted paths).
    """

    name: str
    strategy: RunSourceRefConfig
    indicators: list[RunIndicatorSourceConfig]
    ranking: RankingConfig
    schema_version: int = CONFIG_SCHEMA_VERSION
    data: DataConfig = field(default_factory=lambda: DataConfig(arrays=["OHLCV"]))
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
