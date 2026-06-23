from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.additive_invariance import assert_additive_invariance
from aegis_runtime.futures_roots import validate_bare_root

INSTRUMENT_ID_LEVEL = "instrument_id"
_EXPOSURE_TOLERANCE = 1e-9
_DIRECTIONS = frozenset({"longonly", "shortonly", "both"})


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
    lookback_bars: int = 0
    # Bare continuous-future root symbols (e.g. ``("ES",)``), declared identically to
    # research's ``DataConfig.futures``. Each is materialised on demand as an adjusted
    # continuous series (Path A); venue and currency are catalog-authoritative from its
    # dated legs, so a root carries no venue. Excluded from the native-id union — the
    # legs load dynamically via the chain, not as static natives.
    futures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_instrument_ids(self.instrument_ids, "DataContract.instrument_ids")
        _validate_bare_roots(self.futures, "DataContract.futures")


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
    gross_cap: float
    net_cap: float | None
    direction: str


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
        continuous: list[InstrumentId] = []
        for root in self.contract.futures:
            matches = [
                instrument_id
                for instrument_id in self.contract.instrument_ids
                if instrument_id.symbol.value == root
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"continuous-future root {root!r} is ambiguous: it matches instrument ids "
                    f"{[match.value for match in matches]}; a continuous root must resolve to "
                    f"exactly one column so the additive-invariance re-base targets it alone"
                )
            continuous.extend(matches)
        return tuple(continuous)

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
        validate_exposure(
            weights,
            gross_cap=self._plan.gross_cap,
            net_cap=self._plan.net_cap,
            direction=self._plan.direction,
        )
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


def validate_exposure(
    allocations: pd.DataFrame,
    *,
    gross_cap: float,
    net_cap: float | None = None,
    direction: str = "both",
) -> None:
    if gross_cap <= 0:
        raise ValueError(f"gross_cap must be > 0; got {gross_cap!r}")
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(_DIRECTIONS)}; got {direction!r}")
    if net_cap is None:
        net_cap = gross_cap
    if allocations.empty or len(allocations.columns) == 0:
        return
    decided = allocations.to_numpy(dtype=float, copy=False)
    _assert_sign_consistent(decided, direction)
    gross = allocations.abs().sum(axis=1)
    if (gross > gross_cap + _EXPOSURE_TOLERANCE).any():
        raise ValueError(
            f"gross exposure Σ|wᵢ| {float(gross.max())} exceeds gross_cap {gross_cap}"
        )
    net = allocations.sum(axis=1).abs()
    if (net > net_cap + _EXPOSURE_TOLERANCE).any():
        raise ValueError(f"net exposure |Σwᵢ| {float(net.max())} exceeds net_cap {net_cap}")


def _assert_sign_consistent(decided: np.ndarray, direction: str) -> None:
    if direction == "longonly":
        offenders = decided < -_EXPOSURE_TOLERANCE
        guard = "≥ 0"
    elif direction == "shortonly":
        offenders = decided > _EXPOSURE_TOLERANCE
        guard = "≤ 0"
    else:
        return
    if offenders.any():
        offending = float(decided[offenders][0])
        raise ValueError(
            f"target_weights has weight {offending} violating direction {direction!r} "
            f"(requires wᵢ {guard})"
        )
