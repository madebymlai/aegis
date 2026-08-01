from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from typing import Annotated, Any

import numpy as np
import pandas as pd
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    with_config,
)

from aegis_runtime.domain.component_inputs import ComponentStrategyInputs
from aegis_runtime.domain.currency import CurrencyConversion
from aegis_runtime.domain.drift_band import DriftBand
from aegis_runtime.domain.exposure_validation import ExposureLimits, validate_exposure
from aegis_runtime.domain.futures_roots import validate_bare_root
from aegis_runtime.domain.market_data import MarketDataBundle
from aegis_runtime.execution.roll_sensitivity import compute_roll_checked_weights

INSTRUMENT_ID_LEVEL = "instrument_id"

# The sleeve weight contract: emitted weights are fractions of sleeve NAV, so a
# bundle's gross exposure (Σ|wᵢ|) never exceeds 1.0 — scale is not the sleeve's
# decision. The book allocator is the only leverager; the book's own ceiling
# lives in aegis-trader book.toml and flows through its own ExposureLimits.
# Sleeve enforcement sites pass this explicitly; it must never become a default
# parameter of ExposureLimits (a default would leak sleeve policy into the book
# path). (aegis-rd-ui1m)
SLEEVE_GROSS_LIMIT = 1.0

# The only continuous-futures re-basing algebras Aegis supports. Forward modes are
# rejected everywhere (research never materialises them), so a bundle can only
# declare what a locked Run can actually have used.
SUPPORTED_ADJUSTMENT_MODES = (
    ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
)

# The closed mark-mode wire vocabulary (aegis-rd-tggo.3). The runtime owns only
# the serialization slot; resolution semantics live in aegis-data's marking seam.
RECORDED_MARK_MODES = ("LAST", "MID", "QUOTE")


class MissingIndexPolicy(str, Enum):
    NAN = "nan"
    DROP = "drop"
    RAISE = "raise"


# ── Wire vocabulary ────────────────────────────────────────────────────────
#
# The serialized Execution Bundle is the research→live seam, so each field's
# wire form is declared exactly once, as an annotation on the type that owns it,
# and both directions are derived from it — there is no second module restating
# the payload shape. Nautilus types are adapted through `Annotated` hooks rather
# than `__get_pydantic_core_schema__`: we do not own them and need no JSON
# Schema, which is pydantic's documented cue to prefer the annotation form.

WireInstrumentId = Annotated[
    InstrumentId,
    BeforeValidator(lambda v: InstrumentId.from_str(v) if isinstance(v, str) else v),
    PlainSerializer(lambda v: v.value, return_type=str),
]


def _wire_adjustment_mode(
    mode: ContinuousFutureAdjustmentType,
) -> ContinuousFutureAdjustmentType:
    """The Nautilus enum has forward members; the wire vocabulary does not."""
    if mode not in SUPPORTED_ADJUSTMENT_MODES:
        supported = sorted(member.value for member in SUPPORTED_ADJUSTMENT_MODES)
        raise ValueError(
            f"{mode.value!r} is not a supported mode; expected one of {supported}"
        )
    return mode


WireAdjustmentMode = Annotated[
    ContinuousFutureAdjustmentType,
    AfterValidator(_wire_adjustment_mode),
    PlainSerializer(lambda v: v.value, return_type=str),
]

WireMissingIndex = Annotated[
    MissingIndexPolicy,
    PlainSerializer(lambda v: v.value, return_type=str),
]

# The bundle types stay stdlib dataclasses: construction keeps raising
# DataContractError from __post_init__, unwrapped. Pydantic validates *into*
# them at the wire boundary only, where bundle_loader translates its errors.
BUNDLE_TYPE_CONFIG = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


class DataContractError(ValueError):
    """The Execution Bundle data contract is malformed or violated."""


class InvalidMissingIndexPolicy(DataContractError):
    """The contract declares an unknown missing-index policy."""


class MarketDataMissingIndexError(DataContractError):
    """Market data contains missing values forbidden by the contract policy."""


@dataclass(frozen=True)
@with_config(BUNDLE_TYPE_CONFIG)
class DataContract:
    # The declared universe, and therefore the rebalance-target set: every id here
    # is either native or continuous (the two projections below partition this
    # tuple), and data-only ``exchange`` legs are excluded from it by the
    # no-overlap rule in ``__post_init__``. Callers take this directly — there is
    # no narrower target set to derive.
    instrument_ids: tuple[WireInstrumentId, ...]
    required_arrays: tuple[str, ...]
    base_currency: str
    timeframe: str
    missing_index: WireMissingIndex
    lookback_bars: int = 0
    # Bare continuous-future root symbols (e.g. ``("ES",)``), declared identically to
    # research's ``DataConfig.futures``. Each root must resolve to exactly one synthetic
    # continuous id in ``instrument_ids`` (e.g. ``ES.XCME``); dated legs still load
    # dynamically via the chain, not as static contract columns.
    futures: tuple[str, ...] = ()
    # Data-only FX conversion legs (e.g. ``EUR/USD.IDEALPRO``), declared identically to
    # research's ``DataConfig.exchange``. They load like any native bar stream but are
    # never compute columns or rebalance targets — their bars convert non-base-quoted
    # tradeables to the book's base currency (research parity) and mark the FX rate
    # sizing reads.
    exchange: tuple[WireInstrumentId, ...] = ()
    # The continuous-futures re-basing algebra the locked Run's frames were actually
    # materialised under — a recorded historical fact, never a current code default.
    # Present iff ``futures`` declares roots. Independent of ``exchange``: both
    # backward modes are valid with or without FX conversion legs.
    adjustment_mode: WireAdjustmentMode | None = None
    # Recorded mark modes (aegis-rd-tggo.3): how each leg's mark was resolved in
    # research (LAST / MID / QUOTE), pinned at export so live subscribes exactly
    # the mark the run validated and never re-derives it. Keys are declared
    # loadable ids; continuous roots and their dated legs are LAST by
    # construction and are never recorded. Only the mark travels — the research
    # fill/sim projection is never serialized.
    mark_modes: Mapping[WireInstrumentId, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_instrument_ids(self.instrument_ids, "DataContract.instrument_ids")
        object.__setattr__(
            self,
            "missing_index",
            _coerce_missing_index_policy(self.missing_index),
        )
        _validate_bare_roots(self.futures, "DataContract.futures")
        _continuous_instrument_ids(self.instrument_ids, self.futures)
        _validate_adjustment_mode(self.adjustment_mode, self.futures)
        _validate_instrument_ids(self.exchange, "DataContract.exchange")
        overlap = sorted(
            instrument_id.value
            for instrument_id in set(self.exchange) & set(self.instrument_ids)
        )
        if overlap:
            raise ValueError(
                "DataContract.exchange legs must be data-only, not tradeable "
                f"instrument_ids: {overlap}"
            )
        _validate_mark_modes(self.mark_modes, self.loadable_instrument_ids)

    @property
    def continuous_instrument_ids(self) -> tuple[InstrumentId, ...]:
        """The declared synthetic continuous ids, one for each bare root."""
        return _continuous_instrument_ids(self.instrument_ids, self.futures)

    @property
    def native_instrument_ids(self) -> tuple[InstrumentId, ...]:
        """The declared ids that load as static columns — continuous ids excluded.

        A continuous-future root's synthetic id (e.g. ``ES.XCME``) lives in
        ``instrument_ids`` for band/identity resolution, but its bars arrive
        dynamically through the leg chain, not as a static native column. Callers that
        warm, subscribe, or union the loadable natives take this, not ``instrument_ids``.
        """
        continuous = set(self.continuous_instrument_ids)
        return tuple(
            instrument_id
            for instrument_id in self.instrument_ids
            if instrument_id not in continuous
        )

    @property
    def loadable_instrument_ids(self) -> tuple[InstrumentId, ...]:
        """Every id that loads as a static bar stream: the native tradeables plus
        the data-only FX conversion legs. Callers that warm, subscribe, or union
        what a backtest/live node must load take this; compute columns stay
        ``instrument_ids``."""
        return (*self.native_instrument_ids, *self.exchange)


@dataclass(frozen=True)
@with_config(BUNDLE_TYPE_CONFIG)
class BundleManifest:
    run_id: str
    role: str
    candidate_key: str
    component_source_hashes: Mapping[str, str]
    instrument_ids: tuple[WireInstrumentId, ...]

    def __post_init__(self) -> None:
        _validate_instrument_ids(self.instrument_ids, "BundleManifest.instrument_ids")


@dataclass(frozen=True)
@with_config(BUNDLE_TYPE_CONFIG)
class ComponentSpec:
    family: str
    component_id: str
    module: str
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    params: Mapping[str, Any]


@dataclass(frozen=True)
@with_config(BUNDLE_TYPE_CONFIG)
class LockedExecutionPlan:
    strategy: ComponentSpec
    indicators: tuple[ComponentSpec, ...]
    instrument_bands: Mapping[WireInstrumentId, DriftBand]
    direction: str
    # Derived at construction from `direction`; never serialized.
    _exposure_limits: Annotated[ExposureLimits, Field(exclude=True)] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for instrument_id, band in self.instrument_bands.items():
            if not isinstance(instrument_id, InstrumentId):
                raise ValueError(
                    "LockedExecutionPlan.instrument_bands keys must be InstrumentId values"
                )
            if not isinstance(band, DriftBand):
                raise ValueError(
                    "LockedExecutionPlan.instrument_bands values must be DriftBand values"
                )
        # An illegal direction fails here — at plan construction (bundle load) —
        # not on the first weight computation. Gross is the fixed sleeve contract,
        # never a locked number.
        object.__setattr__(
            self,
            "_exposure_limits",
            ExposureLimits(SLEEVE_GROSS_LIMIT, None, self.direction),
        )

    @property
    def exposure_limits(self) -> ExposureLimits:
        """This plan's Exposure Limits: the unit-gross sleeve contract plus the
        locked direction."""
        return self._exposure_limits


class ExecutionBundle:
    def __init__(
        self,
        *,
        contract: DataContract,
        manifest: BundleManifest,
        plan: LockedExecutionPlan,
    ) -> None:
        _validate_instrument_band_contract(contract=contract, plan=plan)
        self.contract = contract
        self.manifest = manifest
        self._plan = plan

    @property
    def direction(self) -> str:
        """The locked plan's allowed exposure direction
        (``longonly`` / ``shortonly`` / ``both``)."""
        return self._plan.direction

    @property
    def instrument_bands(self) -> Mapping[InstrumentId, DriftBand]:
        """Per-instrument drift bands validated by research for this bundle."""
        return self._plan.instrument_bands

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None,
    ) -> pd.DataFrame:
        """Compute base-currency weights proven insensitive to native roll probes.

        The data layer materialises and re-bases continuous series upstream. This
        method accepts that native window, guards the decision against the contract's
        declared roll mode, and requires the explicit conversion so an already
        converted panel cannot be silently reinterpreted as native.
        """
        return compute_roll_checked_weights(
            contract=self.contract,
            native_window=native_prices,
            decide=partial(
                self._decide_weights,
                currency_conversion=currency_conversion,
            ),
        )

    def _decide_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None,
    ) -> pd.DataFrame:
        prices = (
            native_prices
            if currency_conversion is None
            else currency_conversion.apply(native_prices)
        )
        _validate_market_data(prices, self.contract)
        close = prices.array("Close")
        n_bars = len(close)
        lookback = self.contract.lookback_bars
        if n_bars < lookback:
            raise ValueError(
                f"supplied window has {n_bars} bars, but bundle requires "
                f"at least {lookback} lookback bars"
            )
        index = close.index
        n_candidates = 1
        n_symbols = len(self.contract.instrument_ids)
        expected_shape = (n_bars, n_candidates * n_symbols)
        data = _slice_data(prices, index, self.contract.required_arrays)
        indicator_outputs = _compute_indicators(
            self._plan.indicators,
            data=data,
            expected_shape=expected_shape,
        )
        strategy_module = _load_component_module(self._plan.strategy.module)
        strategy_inputs = ComponentStrategyInputs(
            data=data,
            indicators=indicator_outputs,
            n_candidates=n_candidates,
            n_symbols=n_symbols,
            metadata={
                "strategy_id": self._plan.strategy.component_id,
                "indicator_ids": [spec.component_id for spec in self._plan.indicators],
            },
        )
        raw = strategy_module.run(
            strategy_inputs,
            n_candidates=n_candidates,
            **_candidate_param_lists(self._plan.strategy.params, n_candidates),
        )
        arr = _validated_array(
            raw,
            expected_shape=expected_shape,
            label=f"strategy {self._plan.strategy.component_id} allocation",
        )
        weights = pd.DataFrame(
            arr[:, :n_symbols], index=close.index, columns=close.columns
        )
        weights.columns.name = INSTRUMENT_ID_LEVEL
        _assert_latest_row_not_nan(weights)
        validate_exposure(weights, self._plan.exposure_limits)
        return weights


def _validate_instrument_ids(
    instrument_ids: Sequence[InstrumentId], label: str
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for instrument_id in instrument_ids:
        if not isinstance(instrument_id, InstrumentId):
            raise ValueError(f"{label} must contain Nautilus InstrumentId values")
        if instrument_id.value in seen:
            duplicates.add(instrument_id.value)
        seen.add(instrument_id.value)
    if duplicates:
        raise ValueError(f"{label} contains duplicates: {sorted(duplicates)}")


def _coerce_missing_index_policy(value: object) -> MissingIndexPolicy:
    try:
        return MissingIndexPolicy(value)
    except ValueError:
        allowed = [policy.value for policy in MissingIndexPolicy]
        raise InvalidMissingIndexPolicy(
            f"DataContract.missing_index must be one of {allowed}; got {value!r}"
        ) from None


def _validate_instrument_band_contract(
    *, contract: DataContract, plan: LockedExecutionPlan
) -> None:
    contract_ids = set(contract.instrument_ids)
    band_ids = set(plan.instrument_bands)
    missing = sorted(instrument_id.value for instrument_id in contract_ids - band_ids)
    extra = sorted(instrument_id.value for instrument_id in band_ids - contract_ids)
    if missing or extra:
        raise ValueError(
            "LockedExecutionPlan.instrument_bands must match DataContract.instrument_ids; "
            f"missing={missing}, extra={extra}"
        )


def _validate_adjustment_mode(
    mode: ContinuousFutureAdjustmentType | None,
    futures: Sequence[str],
) -> None:
    if mode is None:
        if futures:
            raise DataContractError(
                "DataContract.futures declares continuous roots "
                f"{sorted(futures)} but no adjustment_mode; the mode the locked "
                "Run materialised under is a required fact"
            )
        return
    if not futures:
        raise DataContractError(
            "DataContract.adjustment_mode is set but futures declares no "
            "continuous roots; a mode without futures is meaningless"
        )
    if not isinstance(mode, ContinuousFutureAdjustmentType):
        raise DataContractError(
            "DataContract.adjustment_mode must be a Nautilus "
            f"ContinuousFutureAdjustmentType; got {mode!r}"
        )
    if mode not in SUPPORTED_ADJUSTMENT_MODES:
        supported = sorted(member.value for member in SUPPORTED_ADJUSTMENT_MODES)
        raise DataContractError(
            f"DataContract.adjustment_mode {mode.value!r} is unsupported; "
            f"only backward modes {supported} are materialisable"
        )


def _validate_mark_modes(
    mark_modes: Mapping[InstrumentId, str],
    loadable_instrument_ids: Sequence[InstrumentId],
) -> None:
    unknown_modes = sorted(
        f"{instrument_id.value}={mode!r}"
        for instrument_id, mode in mark_modes.items()
        if mode not in RECORDED_MARK_MODES
    )
    if unknown_modes:
        raise DataContractError(
            "DataContract.mark_modes carries modes outside the closed set "
            f"{RECORDED_MARK_MODES}: {unknown_modes}"
        )
    undeclared = sorted(
        instrument_id.value
        for instrument_id in mark_modes
        if instrument_id not in set(loadable_instrument_ids)
    )
    if undeclared:
        raise DataContractError(
            "DataContract.mark_modes records marks for ids the contract does "
            f"not load: {undeclared}"
        )


def _validate_bare_roots(roots: Sequence[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for root in roots:
        validate_bare_root(root)
        if root in seen:
            duplicates.add(root)
        seen.add(root)
    if duplicates:
        raise ValueError(f"{label} contains duplicate roots: {sorted(duplicates)}")


def _continuous_instrument_ids(
    instrument_ids: Sequence[InstrumentId],
    roots: Sequence[str],
) -> tuple[InstrumentId, ...]:
    continuous: list[InstrumentId] = []
    for root in roots:
        matches = [
            instrument_id
            for instrument_id in instrument_ids
            if instrument_id.symbol.value == root
        ]
        if not matches:
            raise ValueError(
                f"continuous-future root {root!r} has no matching instrument_id; "
                "expected exactly one synthetic continuous id in DataContract.instrument_ids"
            )
        if len(matches) > 1:
            raise ValueError(
                f"continuous-future root {root!r} is ambiguous: it matches instrument ids "
                f"{[match.value for match in matches]}; a continuous root must resolve to "
                f"exactly one column so the roll-sensitivity probe re-bases it alone"
            )
        continuous.append(matches[0])
    return tuple(continuous)


def _compute_indicators(
    indicators: Sequence[ComponentSpec],
    *,
    data: MarketDataBundle,
    expected_shape: tuple[int, int],
) -> dict[str, np.ndarray]:
    outputs: dict[str, np.ndarray] = {}
    for spec in indicators:
        module = _load_component_module(spec.module)
        result = module.run(
            data, n_candidates=1, **_candidate_param_lists(spec.params, 1)
        )
        if not isinstance(result, Mapping):
            raise TypeError(f"indicator {spec.component_id!r} must return a mapping")
        missing = sorted(set(spec.output_names) - set(result))
        unknown = sorted(set(result) - set(spec.output_names))
        if missing or unknown:
            raise ValueError(
                f"indicator {spec.component_id!r} output mismatch; "
                f"missing={missing}, unknown={unknown}"
            )
        for name in spec.output_names:
            if name in outputs:
                raise ValueError(f"duplicate indicator output {name!r}")
            outputs[name] = _validated_array(
                result[name],
                expected_shape=expected_shape,
                label=f"indicator output {name!r}",
            )
    return outputs


def _candidate_param_lists(
    params: Mapping[str, Any], n_candidates: int
) -> dict[str, list[Any]]:
    return {name: [value] * n_candidates for name, value in params.items()}


def _load_component_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _slice_data(
    data: MarketDataBundle, index: pd.Index, required_arrays: Sequence[str]
) -> MarketDataBundle:
    return MarketDataBundle(
        {name: data.array(name).loc[index] for name in required_arrays}
    )


def _validate_market_data(prices: MarketDataBundle, contract: DataContract) -> None:
    required = set(contract.required_arrays)
    supplied = set(prices.arrays)
    missing_arrays = sorted(required - supplied)
    extra_arrays = sorted(supplied - required)
    if missing_arrays or extra_arrays:
        raise ValueError(
            "market data array mismatch against bundle contract: "
            f"missing={missing_arrays}, extra={extra_arrays}"
        )
    for name in contract.required_arrays:
        frame = prices.array(name)
        actual = tuple(frame.columns)
        if actual != contract.instrument_ids:
            raise ValueError(
                f"market data array {name!r} instrument_ids {actual} do not match "
                f"contract instrument_ids {contract.instrument_ids}"
            )
        if not frame.index.is_unique:
            raise ValueError(f"market data array {name!r} index must be unique")
        if (
            contract.missing_index is not MissingIndexPolicy.NAN
            and frame.isna().any().any()
        ):
            raise MarketDataMissingIndexError(
                f"market data array {name!r} contains NaN under "
                f"missing_index={contract.missing_index.value!r}"
            )
    first_index = prices.array(contract.required_arrays[0]).index
    for name in contract.required_arrays[1:]:
        if not prices.array(name).index.equals(first_index):
            raise ValueError("market data arrays must share one index")


def _validated_array(
    value: Any, *, expected_shape: tuple[int, int], label: str
) -> np.ndarray:
    arr = np.asarray(value)
    if arr.shape != expected_shape:
        raise ValueError(
            f"{label} has expected shape {expected_shape}; actual shape {arr.shape}"
        )
    return arr


def _assert_latest_row_not_nan(weights: pd.DataFrame) -> None:
    if len(weights) == 0:
        return
    latest = weights.iloc[-1]
    if latest.isna().any():
        raise ValueError(
            "latest weight row contains NaN; warmup may be insufficient "
            f"(lookback_bars={weights.shape[0]})"
        )
