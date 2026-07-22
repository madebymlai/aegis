from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, get_args

import pandas as pd
from aegis_data.marking import DeclaredMarkingResolver, MarkMode, split_mark_token
from aegis_runtime import DriftBand
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import AfterValidator, ConfigDict, Field, model_validator
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.authoring_fields import (
    ComponentIdStr,
    NonEmptyStr,
    NonNegativeCash,
    NonNegativeInt,
    NonNegativeRate,
    PositiveCash,
    PositiveInt,
    RootSymbol,
    RunName,
    TimedeltaStr,
    UnitInterval,
    has_data_array_token_shape,
)

# v11 (aegis-rd-ui1m): portfolio.gross_cap / portfolio.net_cap removed — the
# exposure envelope is the fixed unit-gross sleeve contract, not config.
RunConfigSchemaVersion = Literal[11]
CONFIG_SCHEMA_VERSION: int = get_args(RunConfigSchemaVersion)[0]
OHLCV_ARRAYS = ("Open", "High", "Low", "Close", "Volume")
# This is intentionally a shortcut catalog, not a universal feature catalog.
# Full VBT feature names are source-specific and discovered from native_data.features.
DATA_ARRAY_SHORTCUTS = {"OHLCV": OHLCV_ARRAYS}

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
# Declared mark modes (aegis-rd-tggo.2): the closed LAST/MID/QUOTE set, spelled
# as a token on the tradeable id (``UEQC.IBIS:QUOTE``) and parsed once at
# config load. aegis-data's marking seam owns the grammar and the resolution.
MarkModeName = Literal["LAST", "MID", "QUOTE"]
MARK_MODES = set(get_args(MarkModeName))
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
    # Parsed mark-mode declarations (aegis-rd-tggo.2): filled from the optional
    # ``:MODE`` token on ``instruments`` entries (``UEQC.IBIS:QUOTE``), keyed by
    # the bare id. The token IS the authoring surface — this field is its parsed
    # form (present so a config lock round-trips), not a second place to declare.
    mark_modes: dict[str, MarkModeName] = field(default_factory=dict)
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

    @property
    def effective_arrays(self) -> tuple[str, ...]:
        return expand_data_arrays(self.arrays)

    @property
    def native_instrument_ids(self) -> tuple[str, ...]:
        """Native Nautilus InstrumentIds requested from the catalog/port."""
        return tuple(dict.fromkeys([*self.instruments, *self.exchange]))

    def marking_resolver(self) -> DeclaredMarkingResolver:
        """Build the run's marking policy from its explicit declarations."""
        return DeclaredMarkingResolver(
            declared={
                **{InstrumentId.from_str(value): MarkMode.MID for value in self.exchange},
                **{
                    InstrumentId.from_str(value): MarkMode(mode)
                    for value, mode in self.mark_modes.items()
                },
            }
        )

    @model_validator(mode="after")
    def _validate_conditional_requireds(self) -> DataConfig:
        """Cross-field requiredness for the native Nautilus catalog contract."""
        _parse_mark_declarations(self)
        _require_catalog_ids(self)
        return self


def _parse_mark_declarations(config: DataConfig) -> None:
    """Split the optional ``:MODE`` token off each tradeable id (aegis-rd-tggo.2).

    The mark mode is declared at the single point the instrument is named;
    parsed once here into ``mark_modes`` so every downstream consumer keeps
    seeing bare native ids.  A token that contradicts an already-recorded mode
    fails closed; ``exchange`` legs are conversion-only and take no token.
    """
    declared: dict[str, str] = dict(config.mark_modes)
    bare_ids: list[str] = []
    for value in config.instruments:
        spelled, mode = split_mark_token(value)
        bare_ids.append(spelled)
        if mode is None:
            continue
        recorded = declared.get(spelled)
        if recorded is not None and recorded != mode.value:
            raise ValueError(
                f"conflicting mark modes for {spelled!r}: token declares "
                f"{mode.value}, mark_modes records {recorded}"
            )
        declared[spelled] = mode.value
    for value in config.exchange:
        _, mode = split_mark_token(value)
        if mode is not None:
            raise ValueError(
                f"exchange legs are conversion-only and take no mark-mode token: {value!r}"
            )
    # Frozen pydantic dataclass: the one sanctioned rewrite point, inside its
    # own validator, before the config is seen anywhere else.
    object.__setattr__(config, "instruments", bare_ids)
    object.__setattr__(config, "mark_modes", declared)


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
    return merge_data_arrays(*(DATA_ARRAY_SHORTCUTS.get(token, (token,)) for token in arrays))


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


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class SignalConfig:
    policy: SignalPolicy = "long_only_hysteresis"
    long_entry_threshold: float = 0.55
    long_exit_threshold: float = 0.50
    execution_timing: SignalExecutionTiming = "next_open"


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class InstrumentBandConfig:
    up: NonNegativeRate
    down: NonNegativeRate
    # Unset inherits the sleeve-wide ``band_destination_fraction``.
    destination_fraction: UnitInterval | None = None


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
    # Per-name no-trade band as a fraction of NAV (live-research parity). A
    # position is left to drift and is rebalanced to target only once its weight
    # crosses the directional width: ``band_up`` gates trims and ``band_down``
    # gates adds. Enforced in the research sim by the shared DriftBand gate
    # against the DRIFTED weight, so the same gate yields the same trades in
    # both paths. This - not an in-strategy buffer - is the turnover /
    # "few-trades" lever; a slow signal makes the target stable, so target ~
    # realized stays inside the band and the book holds. Default 0 = rebalance
    # every executable bar (the historical behaviour).
    band_up: NonNegativeRate = 0.0
    band_down: NonNegativeRate = 0.0
    # Where a band breach trades to: 0.0 stops at the band edge (the
    # proportional-cost optimum), 1.0 trades all the way to target (the
    # per-order-fee optimum, the historical behaviour). Interior values
    # amortize a fixed fee over a larger trade while keeping headroom
    # inside the band. Overridable per tradeable via ``band_overrides``.
    band_destination_fraction: UnitInterval = 1.0
    # Per-tradeable override for the sleeve-wide no-trade band. Keys are the
    # configured tradeable names: native InstrumentId strings from data.instruments
    # or bare roots from data.futures. Validation against the run's tradeable
    # universe lives in the coordinator, where data and portfolio are both visible.
    band_overrides: dict[str, InstrumentBandConfig] = field(default_factory=dict)
    # Short financing carry: flat annual rates. Effective net carry = borrow - rebate,
    # charged only on short legs (see ADR-0008). The non-zero borrow default means carry
    # is ON by default; a long-only book has no short legs and is unaffected.
    short_borrow_rate: NonNegativeRate = 0.005
    short_rebate_rate: NonNegativeRate = 0.0
    # Margin interest: flat annual debit rate charged on negative group cash.
    # Positive cash earns nothing, and explicit 0.0 is the sanctioned mechanics-test
    # opt-out. Default is the pinned IBKR-IE EUR FIRST-TIER debit rate (BM + 1.5%,
    # re-pinned 2026-07-06): the live account is ~5k EUR, so every debit sits below
    # the 90k tier break. Keep in sync with aegis-trader/book.toml
    # [costs.margin_interest] - same pin, two homes.
    margin_interest_rate: NonNegativeRate = 0.0367
    # The exposure envelope is NOT configurable: sleeve weights are unit-gross by
    # contract (aegis_runtime.bundle.SLEEVE_GROSS_LIMIT; aegis-rd-ui1m) — the book
    # allocator is the only leverager. Only direction is declared per run.
    # Required (validation rejects a config missing it); no silent long-only default.
    direction: Literal["longonly", "shortonly", "both"] = field(kw_only=True)

    def resolved_band_for(self, key: str) -> DriftBand:
        """Resolve one instrument's no-trade band: an override beats the sleeve default.

        *key* is the instrument's single override key — the one the author writes in
        ``band_overrides``: a native InstrumentId string, or a continuous future's bare
        ``data.futures`` root. The caller resolves the instrument to that one canonical
        key (no try-this-then-that); an exact miss means no override, so the sleeve-wide
        ``band_up``/``band_down`` applies. This is the single authority for that
        precedence — both research export and the sim resolve here.
        """
        override = self.band_overrides.get(key)
        if override is None:
            return DriftBand(
                up=self.band_up,
                down=self.band_down,
                destination_fraction=self.band_destination_fraction,
            )
        return DriftBand(
            up=override.up,
            down=override.down,
            destination_fraction=(
                self.band_destination_fraction
                if override.destination_fraction is None
                else override.destination_fraction
            ),
        )


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ReportConfig:
    freq: TimedeltaStr = "1D"
    year_freq: TimedeltaStr = "252D"
    # Extra opt-in custom metrics to compute and report per candidate alongside the
    # ranker (the ranking metric is pulled automatically). Named ids are cross-checked
    # against the metric registry; each becomes a reported column and can serve as a
    # promotion gate read post-hoc. This is how the carry pole reports its
    # family-membership and tail gates next to its income ranker without re-running.
    metrics: list[str] = field(default_factory=list)

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
    min_trades: NonNegativeInt = 0


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class OptimizationConfig:
    search: Literal["grid", "random"]
    observation_block_bars: PositiveInt
    random_subset: PositiveInt | None = None
    seed: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _random_needs_subset_and_seed(self):
        if self.search == "random":
            if self.random_subset is None:
                raise ValueError("random_subset is required when optimization.search is 'random'")
            if self.seed is None:
                raise ValueError(
                    "seed is required when optimization.search is 'random' "
                    "so sampled evidence is deterministic"
                )
        if self.search == "grid" and self.random_subset is not None:
            raise ValueError("random_subset is only valid when optimization.search is 'random'")
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

    run_id: NonEmptyStr
    candidate_id: NonEmptyStr

    @model_validator(mode="before")
    @classmethod
    def _coerce_handle(cls, data: Any) -> Any:
        """Normalize a scalar ``run_id[:role]`` handle to the mapping shape."""
        if isinstance(data, str):
            run_id, _, role = data.partition(":")
            if not run_id:
                raise ValueError("run_id must not be empty")
            if role and role not in LOCK_ROLES:
                roles_label = ", ".join(LOCK_ROLES)
                raise ValueError(f"role must be one of: {roles_label} (got {role!r})")
            return {"run_id": run_id, "candidate_id": role or DEFAULT_LOCK_ROLE}
        return data


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class RunConfig:
    """Whole-tree pydantic dataclass: one ``TypeAdapter(RunConfig).validate_python(raw)``
    validates the entire run config and accumulates all structural errors across sections.

    The model is the structural authoring contract. Runtime registry and whole-config
    selection checks run only after this value has been constructed.
    """

    name: RunName
    strategy: RunSourceRefConfig
    indicators: list[RunIndicatorSourceConfig]
    ranking: RankingConfig
    schema_version: RunConfigSchemaVersion = field(kw_only=True)
    # Required (keyword-only so they can sit among defaulted fields): a run must declare
    # its data (which requires explicit arrays — no silent OHLCV default) and its
    # portfolio (which requires an explicit direction — no silently long-only default).
    data: DataConfig = field(kw_only=True)
    portfolio: PortfolioConfig = field(kw_only=True)
    report: ReportConfig = field(default_factory=ReportConfig)
    optimization: OptimizationConfig = field(kw_only=True)
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
