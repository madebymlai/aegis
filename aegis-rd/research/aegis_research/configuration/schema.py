from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, get_args

import pandas as pd
from pydantic import AfterValidator, ConfigDict, Field, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.configuration.field_types import (
    IDENTIFIER_RE,  # noqa: F401 — re-exported for configuration
    ComponentIdStr,
    NonEmptyStr,
    NonNegativeCash,
    NonNegativeInt,
    NonNegativeRate,
    PositiveCash,
    PositiveInt,
    RootSymbol,
    StrictFloat,
    TimedeltaStr,
    UnitInterval,
)

CONFIG_SCHEMA_VERSION = 10
OHLCV_ARRAYS = ("Open", "High", "Low", "Close", "Volume")
# This is intentionally a shortcut catalog, not a universal feature catalog.
# Full VBT feature names are source-specific and discovered from native_data.features.
DATA_ARRAY_SHORTCUTS = {"OHLCV": OHLCV_ARRAYS}
_DATA_WINDOW_REQUIRED_FIELDS = ("start", "end", "timeframe")

PORTFOLIO_DIRECTIONS = {"longonly", "shortonly", "both"}
# For each catalog below the Literal is the field type, the set is the
# facade-exported catalog; get_args keeps them one source.
SignalPolicy = Literal["long_only_hysteresis"]
SIGNAL_POLICIES = set(get_args(SignalPolicy))
SignalExecutionTiming = Literal["next_open", "next_close", "same_close"]
SIGNAL_EXECUTION_TIMINGS = set(get_args(SignalExecutionTiming))
# VBT's Data.align_index / align_columns contract.
MissingPolicy = Literal["nan", "drop", "raise"]
MISSING_POLICIES = set(get_args(MissingPolicy))
Degradation = Literal[
    "duplicate_index",
    "missing_rows",
    "non_monotonic_index",
    "skipped_instrument_ids",
]
DATA_QUALITY_DEGRADATIONS = set(get_args(Degradation))
FORWARD_OPTIMIZATION_REQUIRED_MESSAGE = (
    "is required; fixed/non-optimized strategy runs are removed from the forward "
    "run contract; use optimization.search and optimization.split"
)

# ── Forward-contract prepass overlay ──────────────────────────────────────────
# Rules that amend the raw pydantic model for the forward contract: pydantic
# alone declares ``optimization`` optional and gives ``schema_version`` a
# default, but the validation prepass requires both. This is the single home
# consumed by BOTH the prepass (``validation._prepass_raw_config``) and the
# config-schema guide renderer, so the documented requiredness cannot fork from
# the enforced requiredness (ADR-0019).
PREPASS_REQUIRED_FIELDS: dict[str, str] = {
    "optimization": FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
}
"""Top-level fields the prepass requires regardless of the model default,
mapped to the validation-issue message emitted when the field is absent."""

PREPASS_CONST_FIELDS: dict[str, object] = {
    "schema_version": CONFIG_SCHEMA_VERSION,
}
"""Top-level fields whose value the prepass fixes (const)."""

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
    allowed_degradations: list[Degradation] = field(default_factory=list)


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
    # No schema default — required. Keyword-only so a required field can sit among
    # defaulted ones — every construction site splats **raw anyway.
    arrays: Annotated[list[ArrayToken], Field(min_length=1)] = field(kw_only=True)
    base_currency: str = "EUR"
    instruments: list[str] = field(default_factory=list)
    exchange: list[str] = field(default_factory=list)
    # Bare continuous-future root symbols (e.g. ``["ES", "KC"]``), not native ids: each
    # is materialised on demand as an adjusted continuous series (Path A), venue and
    # currency catalog-authoritative from its dated legs. Distinct from raw ``instruments``.
    # ``RootSymbol`` rejects venue-qualified ids via the same validator live's DataContract uses.
    futures: list[RootSymbol] = field(default_factory=list)
    start: str | None = None
    end: str | None = None
    timeframe: str = "1D"
    path: str | None = None
    missing_index: MissingPolicy = "raise"
    missing_columns: MissingPolicy = "raise"
    tz_localize: str | bool | None = None
    tz_convert: str | bool | None = None
    skip_on_error: bool = False
    silence_warnings: bool = False
    quality: DataQualityConfig = field(default_factory=DataQualityConfig)

    @property
    def effective_arrays(self) -> tuple[str, ...]:
        return expand_data_arrays(self.arrays)

    @property
    def native_instrument_ids(self) -> tuple[str, ...]:
        """Native Nautilus InstrumentIds requested from the catalog/port."""
        return tuple(dict.fromkeys([*self.instruments, *self.exchange]))

    @model_validator(mode="after")
    def _validate_conditional_requireds(self) -> DataConfig:
        """Cross-field requiredness for the native Nautilus catalog contract."""
        _require_catalog_ids(self)
        _require_catalog_window(self)
        if self.skip_on_error and "skipped_instrument_ids" not in self.quality.allowed_degradations:
            raise ValueError(
                "skip_on_error requires data.quality.allowed_degradations "
                "to include 'skipped_instrument_ids'"
            )
        return self


def _require_catalog_window(config: DataConfig) -> None:
    for field_name in _DATA_WINDOW_REQUIRED_FIELDS:
        if not getattr(config, field_name):
            raise ValueError(f"{field_name} is required for catalog data")


def _require_catalog_ids(config: DataConfig) -> None:
    if not config.instruments and not config.futures:
        raise ValueError(
            "at least one tradeable source is required: set data.instruments "
            "(native ids) and/or data.futures (continuous-future roots)"
        )
    _require_unique_non_empty(config.instruments, "instruments")
    _require_unique_non_empty(config.exchange, "exchange")
    _require_unique_non_empty(
        config.futures, "futures", value_desc="continuous-future root symbols"
    )
    overlaps = sorted(set(config.instruments) & set(config.exchange))
    if overlaps:
        raise ValueError(f"instrument ids cannot be both tradeable and exchange-only: {overlaps}")


def _require_unique_non_empty(
    values: list[str], field_name: str, *, value_desc: str = "native InstrumentId strings"
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must contain non-empty {value_desc}")
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"duplicate {field_name}: {sorted(duplicates)}")


def expand_data_arrays(arrays: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return merge_data_arrays(
        *(DATA_ARRAY_SHORTCUTS.get(token, (token,)) for token in arrays)
    )


def merge_data_arrays(*array_groups: tuple[str, ...]) -> tuple[str, ...]:
    """Merge data-array groups into one duplicate-free tuple, preserving order."""
    merged: list[str] = []
    seen: set[str] = set()
    for group in array_groups:
        for feature in group:
            if feature in seen:
                continue
            merged.append(feature)
            seen.add(feature)
    return tuple(merged)


def has_data_array_token_shape(value: str) -> bool:
    return bool(value) and value.strip() == value and not any(char in "\t\n\r" for char in value)


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunSplitConfig:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    max_splits: PositiveInt = 100
    max_estimated_output_cells: PositiveInt = 25_000_000
    max_public_artifact_bytes: PositiveInt = 10_000_000

    @model_validator(mode="after")
    def _no_set_labels(self):
        if "set_labels" in self.params:
            raise ValueError(
                "set roles are owned by Aegis and assigned positionally "
                "(set 0 selection, set 1 held_out); set_labels is not configurable"
            )
        return self


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class SignalConfig:
    policy: SignalPolicy = "long_only_hysteresis"
    long_entry_threshold: float = 0.55
    long_exit_threshold: float = 0.50
    execution_timing: SignalExecutionTiming = "next_open"


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class PortfolioConfig:
    init_cash: PositiveCash = 10_000.0
    fees: NonNegativeRate = 0.001
    slippage: NonNegativeRate = 0.0005
    # Flat per-order commission in the book's base currency (the broker's
    # per-order MINIMUM, e.g. IBKR's EUR 1.25), charged on every fill on top of
    # ``fees``. Unlike the proportional ``fees``/``slippage``, a fixed charge is
    # absolute, so its drag scales with ``init_cash``: it only carries the real
    # cost when ``init_cash`` is set to the modelled account NAV. Default 0 = off,
    # so a returns-scaled book (the historical behaviour) is unaffected.
    fixed_fee: NonNegativeCash = 0.0
    # Where a target decided from bar t's close fills: ``next_close`` (bar t+1 close,
    # the default), ``next_open`` (bar t+1 open — the only mode needing the Open array),
    # or ``same_close`` (bar t's own close — look-ahead, for mechanics tests). All non-
    # ``next_open`` modes avoid same-bar look-ahead via the engine's from_ago=1 shift.
    fill_timing: SignalExecutionTiming = "next_close"
    # The book's accounting currency. Prices are converted to it upstream in the
    # data layer; a non-base leg additionally pays ``fx_conversion_cost`` per trade.
    base_currency: str = "EUR"
    # Per-conversion FX cost charged on every trade of a non-base-currency leg
    # (the EUR->ccy buy and the ccy->EUR sell). Default 0 = off, so a single-currency
    # book is unaffected.
    fx_conversion_cost: NonNegativeRate = 0.0
    net_cap: NonNegativeRate = 1.0
    # Per-name no-trade band as a fraction of NAV (live-research parity). A position is left
    # to drift and is rebalanced to target only once its weight deviates from target by more
    # than this fraction - the symmetric per-instrument drift band the live rebalancer applies
    # (aegis-trader BookConfig.default_band_up/down). Enforced in the research sim by the
    # shared DriftBand gate against the DRIFTED weight, so the same gate yields the same
    # trades in both paths. This - not an in-strategy buffer - is the turnover / "few-trades"
    # lever; a slow signal makes the target stable, so target ~ realized stays inside the band
    # and the book holds. Default 0 = rebalance every executable bar (the historical behaviour).
    rebalance_band: NonNegativeRate = 0.0
    # Optional asymmetric no-trade band. When omitted, both directions use
    # ``rebalance_band``; when supplied, both directional widths must be present.
    band_up: NonNegativeRate | None = None
    band_down: NonNegativeRate | None = None
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

    @model_validator(mode="after")
    def _validate_directional_band_pair(self) -> PortfolioConfig:
        if (self.band_up is None) != (self.band_down is None):
            raise ValueError("band_up and band_down must be supplied together")
        return self

    @property
    def effective_band_up(self) -> float:
        return self.rebalance_band if self.band_up is None else self.band_up

    @property
    def effective_band_down(self) -> float:
        return self.rebalance_band if self.band_down is None else self.band_down


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ReportConfig:
    min_oos_sharpe: StrictFloat = 0.5
    max_oos_drawdown: UnitInterval = 0.35
    min_oos_trades: NonNegativeInt = 5
    freq: TimedeltaStr = "1D"
    year_freq: TimedeltaStr = "252D"

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
    random_subset: PositiveInt | None = None
    seed: NonNegativeInt | None = None
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
                f"reserved keys {reserved} are managed by Aegis's optimization "
                "layer and must not be passed through optimization.execute, which "
                "forwards raw vbt.parameterized engine kwargs only "
                "(e.g. chunking, engine, progress)"
            )
        return self


# The representative roles a Lock handle may name, in rank order. These mirror the
# roles evidence emits for every Run (candidate_evidence.CANDIDATE_ROLES); the config
# layer keeps its own copy because it must not depend up on the optimization layer.
LOCK_ROLES: tuple[str, ...] = ("best", "median", "worst")
DEFAULT_LOCK_ROLE = "best"


def lock_handle(run_id: str, role: str) -> str:
    """Compose a ``run_id[:role]`` handle for a Lock reference.

    Bare ``run_id`` means the default (best) role.
    Lives beside the Lock parser so the grammar is read and written by
    exactly one module (ADR-0021).
    """
    return run_id if role == DEFAULT_LOCK_ROLE else f"{run_id}:{role}"


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
    candidate_id: NonEmptyStr

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
    # Required (keyword-only so they can sit among defaulted fields): a run must declare
    # its data (which requires explicit arrays — no silent OHLCV default) and its
    # portfolio (which requires an explicit direction — no silently long-only default).
    data: DataConfig = field(kw_only=True)
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
