from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.additive_invariance import assert_additive_invariance
from aegis_runtime.drift_band import DriftBand
from aegis_runtime.exposure_validation import ExposureLimits, validate_exposure
from aegis_runtime.futures_roots import validate_bare_root

INSTRUMENT_ID_LEVEL = "instrument_id"


class MissingIndexPolicy(str, Enum):
    NAN = "nan"
    DROP = "drop"
    RAISE = "raise"


class DataContractError(ValueError):
    """The Execution Bundle data contract is malformed or violated."""


class InvalidMissingIndexPolicy(DataContractError):
    """The contract declares an unknown missing-index policy."""


class MarketDataMissingIndexError(DataContractError):
    """Market data contains missing values forbidden by the contract policy."""


@dataclass(frozen=True)
class MarketDataBundle:
    """Eager value object of materialised Array panels.

    Dict membership is the sole guard — an array is loaded iff it is a key.
    """

    arrays: Mapping[str, pd.DataFrame]

    def array(self, name: str) -> pd.DataFrame:
        try:
            return self.arrays[name]
        except KeyError:
            raise ValueError(f"market data array {name!r} was not supplied") from None


@dataclass(frozen=True)
class DataContract:
    instrument_ids: tuple[InstrumentId, ...]
    required_arrays: tuple[str, ...]
    base_currency: str
    timeframe: str
    missing_index: MissingIndexPolicy
    lookback_bars: int = 0
    # Bare continuous-future root symbols (e.g. ``("ES",)``), declared identically to
    # research's ``DataConfig.futures``. Each root must resolve to exactly one synthetic
    # continuous id in ``instrument_ids`` (e.g. ``ES.XCME``); dated legs still load
    # dynamically via the chain, not as static contract columns.
    futures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_instrument_ids(self.instrument_ids, "DataContract.instrument_ids")
        object.__setattr__(
            self,
            "missing_index",
            _coerce_missing_index_policy(self.missing_index),
        )
        _validate_bare_roots(self.futures, "DataContract.futures")
        _continuous_instrument_ids(self.instrument_ids, self.futures)

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


@dataclass(frozen=True)
class BundleManifest:
    run_id: str
    role: str
    candidate_key: str
    component_source_hashes: Mapping[str, str]
    instrument_ids: tuple[InstrumentId, ...]

    def __post_init__(self) -> None:
        _validate_instrument_ids(self.instrument_ids, "BundleManifest.instrument_ids")


@dataclass(frozen=True)
class ComponentSpec:
    family: str
    component_id: str
    module: str
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    params: Mapping[str, Any]


@dataclass(frozen=True)
class LockedExecutionPlan:
    strategy: ComponentSpec
    indicators: tuple[ComponentSpec, ...]
    instrument_bands: Mapping[InstrumentId, DriftBand]
    gross_cap: float
    net_cap: float | None
    direction: str
    _exposure_limits: ExposureLimits = field(init=False, repr=False, compare=False)

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
        # An illegal caps triple fails here — at plan construction (bundle load) —
        # not on the first weight computation.
        object.__setattr__(
            self,
            "_exposure_limits",
            ExposureLimits(self.gross_cap, self.net_cap, self.direction),
        )

    @property
    def exposure_limits(self) -> ExposureLimits:
        """This plan's validated Exposure Limits, built once from the locked triple."""
        return self._exposure_limits


@dataclass(frozen=True)
class ComponentStrategyInputs:
    data: MarketDataBundle
    indicators: Mapping[str, np.ndarray]
    n_candidates: int
    n_symbols: int
    metadata: dict[str, Any]


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
    def gross_cap(self) -> float:
        """The locked plan's gross-exposure cap (max Σ|wᵢ|) — the
        manifest-grounded source of what research validated for this bundle."""
        return self._plan.gross_cap

    @property
    def net_cap(self) -> float | None:
        """The locked plan's net-exposure cap (max |Σwᵢ|), or ``None`` when the
        plan leaves net exposure bounded only by the gross cap."""
        return self._plan.net_cap

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
        prices: MarketDataBundle,
    ) -> pd.DataFrame:
        weights = self._decide_weights(prices)
        # A continuous-future root is re-based at every roll; reject an allocation that
        # reads its absolute price level (it would silently desync live-vs-research).
        assert_additive_invariance(
            weights=weights,
            recompute=self._decide_weights,
            window=prices,
            continuous_ids=self._continuous_ids(),
        )
        return weights

    def _continuous_ids(self) -> tuple[InstrumentId, ...]:
        """The contract's instrument ids that materialise a declared continuous-future root —
        the columns a roll re-bases.

        Each bare root resolves to the *one* synthetic continuous id whose symbol matches it
        (``ES`` → ``ES.XCME``). A root that matches more than one instrument id is ambiguous —
        the contract cannot tell the continuous root from a same-symbol native (a stock ``ES``),
        and re-basing the native's price column would corrupt the invariance check — so it is
        rejected loudly rather than silently re-basing the wrong column.
        """
        return self.contract.continuous_instrument_ids

    def _decide_weights(
        self,
        prices: MarketDataBundle,
    ) -> pd.DataFrame:
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
        data = _slice_data(prices, index, self.contract.required_arrays)
        indicator_outputs = _compute_indicators(
            self._plan.indicators,
            data=data,
            expected_shape=(len(close), n_candidates * n_symbols),
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
            expected_shape=(len(close), n_candidates * n_symbols),
            label=f"strategy {self._plan.strategy.component_id} allocation",
        )
        weights = pd.DataFrame(arr[:, :n_symbols], index=close.index, columns=close.columns)
        weights.columns.name = INSTRUMENT_ID_LEVEL
        _assert_latest_row_not_nan(weights)
        validate_exposure(weights, self._plan.exposure_limits)
        return weights


def _validate_instrument_ids(instrument_ids: Sequence[InstrumentId], label: str) -> None:
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
            instrument_id for instrument_id in instrument_ids if instrument_id.symbol.value == root
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
                f"exactly one column so the additive-invariance re-base targets it alone"
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
        result = module.run(data, n_candidates=1, **_candidate_param_lists(spec.params, 1))
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
                result[name], expected_shape=expected_shape, label=f"indicator output {name!r}"
            )
    return outputs


def _candidate_param_lists(params: Mapping[str, Any], n_candidates: int) -> dict[str, list[Any]]:
    return {name: [value] * n_candidates for name, value in params.items()}


def _load_component_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _slice_data(
    data: MarketDataBundle, index: pd.Index, required_arrays: Sequence[str]
) -> MarketDataBundle:
    return MarketDataBundle({name: data.array(name).loc[index] for name in required_arrays})


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
        if contract.missing_index is not MissingIndexPolicy.NAN and frame.isna().any().any():
            raise MarketDataMissingIndexError(
                f"market data array {name!r} contains NaN under "
                f"missing_index={contract.missing_index.value!r}"
            )
    first_index = prices.array(contract.required_arrays[0]).index
    for name in contract.required_arrays[1:]:
        if not prices.array(name).index.equals(first_index):
            raise ValueError("market data arrays must share one index")


def _validated_array(value: Any, *, expected_shape: tuple[int, int], label: str) -> np.ndarray:
    arr = np.asarray(value)
    if arr.shape != expected_shape:
        raise ValueError(f"{label} has expected shape {expected_shape}; actual shape {arr.shape}")
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
