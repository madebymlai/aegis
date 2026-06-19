"""Strategy-free per-period rebalance orchestration over injected ports.

The pipeline owns the rebalance path: build each sleeve's runtime market bundle
from a completed-period bar snapshot, run the sleeve Execution Bundles, net
through the rebalancer, size into OrderIntents, record the SleeveLedger, and
return value objects for the Strategy to log and submit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    DataContract,
    ExecutionBundle,
    FuturesRef,
    InstrumentRef,
    ListedRef,
    MarketDataBundle,
)
from aegis_runtime.currency import major_currency

from aegis_trader.bundles.provenance import CapProvenanceError, check_cap_provenance
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import check_account_integrity
from aegis_trader.domain.rebalancer import RebalancePlan, rebalance_plan
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import OrderIntent, ResolvedContractId, SleeveName, WeightDelta

if TYPE_CHECKING:
    from aegis_trader.data.market_data import MarketDataPort
    from aegis_trader.portfolio import BookStatePort


InstrumentResolver = Callable[[InstrumentRef, date], InstrumentId]
RefCurrencyReconciler = Callable[[InstrumentRef, str], str]


class GateOutcome(str, Enum):
    """Outcome of the cap/band gate during a rebalance."""

    PASS = "pass"
    HALT = "halt"
    ERROR = "error"


@dataclass(frozen=True)
class RebalanceSummary:
    """Structured summary of one rebalance decision."""

    nav: float
    num_sleeves: int
    num_targets: int
    num_orders: int
    gate_outcome: GateOutcome
    total_notional: float


class StartupGate(str, Enum):
    """Startup gate responsible for a startup halt."""

    CAP_PROVENANCE = "cap_provenance"
    ACCOUNT_INTEGRITY = "account_integrity"


@dataclass(frozen=True)
class StartupResult:
    """Result of the startup checks that decide whether the book may trade."""

    trading_enabled: bool
    halt_gate: StartupGate | None = None
    halt_reason: str | None = None
    nav: float | None = None
    cash: float | None = None

    @property
    def should_halt(self) -> bool:
        """Whether the Strategy must idle instead of trading."""
        return not self.trading_enabled


@dataclass(frozen=True)
class IdentityResolutionChange:
    """A ref whose current resolved InstrumentId changed as-of a date."""

    ref: InstrumentRef
    previous: InstrumentId
    current: InstrumentId


@dataclass(frozen=True)
class CompletedRebalancePeriod:
    """Completed rebalance-period coordinates for Cache-backed bar reads."""

    period: int
    period_ns: int


@dataclass(frozen=True)
class RebalanceResult:
    """Plain output of one rebalance period."""

    orders: tuple[OrderIntent, ...]
    summary: RebalanceSummary
    halt_reason: str | None = None


class FixtureInstrumentResolver:
    """Deterministic InstrumentRef→InstrumentId resolver for tests/backtests."""

    def __init__(self, mapping: Mapping[InstrumentRef, InstrumentId]) -> None:
        self._mapping = dict(mapping)

    def __call__(self, ref: InstrumentRef, _as_of: date) -> InstrumentId:
        try:
            return self._mapping[ref]
        except KeyError:
            raise ValueError(
                f"InstrumentRef {ref.value!r} is not in the fixture resolver"
            ) from None


class RebalancePipeline:
    """Per-period rebalance orchestrator behind a value-object API.

    Constructor injection keeps the Nautilus lifecycle at the edge: the Strategy
    supplies cache-backed ports and an identity resolver; the pipeline only sees
    canonical InstrumentRefs, plain market bars, and value-object requests.
    """

    def __init__(
        self,
        *,
        book_state: BookStatePort,
        market_data: MarketDataPort,
        book: BookConfig,
        sleeve_to_bundle: Mapping[SleeveName, ExecutionBundle],
        ledger: SleeveLedger,
        resolve_instrument: InstrumentResolver,
        reconcile_ref_currency: RefCurrencyReconciler | None = None,
    ) -> None:
        self._book_state = book_state
        self._market_data = market_data
        self._book = book
        self._sleeve_to_bundle = sleeve_to_bundle
        self._ledger = ledger
        self._resolve_instrument = resolve_instrument
        self._reconcile_ref_currency = reconcile_ref_currency or _identity_currency
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        self._all_refs = frozenset(
            ref
            for bundle in self._sleeve_to_bundle.values()
            for ref in bundle.contract.refs
        )
        self._timeframe_by_ref = _timeframe_by_ref(self._sleeve_to_bundle)
        self._ref_to_instrument_id: dict[InstrumentRef, InstrumentId] = {}
        self._instrument_id_to_ref: dict[str, InstrumentRef] = {}

    @property
    def sleeve_ledger(self) -> SleeveLedger:
        """Cross-period analytics ledger owned by the pipeline."""
        return self._ledger

    @property
    def last_sleeve_weights(self) -> dict[SleeveName, float]:
        """Last allocator-applied sleeve multipliers, for evidence/backtest seams."""
        return dict(self._last_sleeve_weights)

    def initialize_identity(self, as_of: date) -> None:
        """Resolve every sleeve InstrumentRef for the boot date."""
        for ref in sorted(self._all_refs, key=_ref_sort_key):
            self._record_resolution(ref, self._resolve_instrument(ref, as_of))

    def instrument_id_for_ref(self, ref: InstrumentRef) -> InstrumentId:
        """Current venue-specific InstrumentId for an InstrumentRef."""
        instr_id = self._ref_to_instrument_id.get(ref)
        if instr_id is None:
            raise ValueError(
                f"InstrumentRef {ref!r} is not resolved; refusing to act on "
                f"an unidentified instrument"
            )
        return instr_id

    def ref_for_instrument_value(self, instrument_id_value: str) -> InstrumentRef | None:
        """InstrumentRef previously resolved for a Nautilus InstrumentId value."""
        return self._instrument_id_to_ref.get(instrument_id_value)

    def refresh_resolution(self, as_of: date) -> tuple[IdentityResolutionChange, ...]:
        """Re-resolve FuturesRefs and retain inverse mappings for old contracts."""
        changes: list[IdentityResolutionChange] = []
        futures_refs = sorted(
            (ref for ref in self._all_refs if isinstance(ref, FuturesRef)),
            key=_ref_sort_key,
        )
        for ref in futures_refs:
            previous = self.instrument_id_for_ref(ref)
            current = self._resolve_instrument(ref, as_of)
            if current == previous:
                continue
            self._record_resolution(ref, current)
            changes.append(IdentityResolutionChange(ref=ref, previous=previous, current=current))
        return tuple(changes)

    def resolve_contract_id_for_roll(self, ref: InstrumentRef, as_of: date) -> ResolvedContractId:
        """Resolve a roll target and fold the resolved id back to its ref."""
        instrument_id = self._resolve_instrument(ref, as_of)
        self._record_resolution(ref, instrument_id)
        return ResolvedContractId(instrument_id.value)

    def resolved_identity_snapshot(self) -> dict[InstrumentRef, InstrumentId]:
        """Current pipeline-owned identity map for logging and risk wiring."""
        return dict(self._ref_to_instrument_id)

    def startup_check(self) -> StartupResult:
        """Run startup gates and return the decision as a value object."""
        cap_result = self._cap_provenance_startup_result()
        if cap_result is not None:
            return cap_result
        return self._account_integrity_startup_result()

    def _cap_provenance_startup_result(self) -> StartupResult | None:
        try:
            check_cap_provenance(self._book, self._sleeve_to_bundle)
        except CapProvenanceError as exc:
            return StartupResult(
                trading_enabled=False,
                halt_gate=StartupGate.CAP_PROVENANCE,
                halt_reason=str(exc),
            )
        return None

    def _account_integrity_startup_result(self) -> StartupResult:
        try:
            nav = self._book_state.nav()
            cash = self._book_state.cash()
        except Exception as exc:
            return StartupResult(
                trading_enabled=False,
                halt_gate=StartupGate.ACCOUNT_INTEGRITY,
                halt_reason=f"Failed to query book state for integrity check: {exc}",
            )

        report = check_account_integrity(
            nav=nav,
            cash=cash,
            cache_healthy=self._book_state.is_cache_healthy(),
        )
        if not report.healthy:
            return StartupResult(
                trading_enabled=False,
                halt_gate=StartupGate.ACCOUNT_INTEGRITY,
                halt_reason=report.reason or "Unknown integrity failure",
                nav=nav,
                cash=cash,
            )
        return StartupResult(trading_enabled=True, nav=nav, cash=cash)

    def _record_resolution(self, ref: InstrumentRef, instrument_id: InstrumentId) -> None:
        self._ref_to_instrument_id[ref] = instrument_id
        # Deliberately do not delete old inverse entries: a held stale futures
        # contract must still fold back to its continuous FuturesRef for Roll.
        self._instrument_id_to_ref[instrument_id.value] = ref

    def rebalance_period(self, period: CompletedRebalancePeriod) -> RebalanceResult:
        """Run one completed-period rebalance and return orders plus summary."""
        pending = self._compute_sleeve_targets(period)
        nav = self._book_state.nav()
        if not pending:
            return RebalanceResult(
                orders=(),
                summary=_summary(nav, 0, 0, 0, GateOutcome.PASS, 0.0),
            )

        realized_weights = self._book_state.realized_weights()
        try:
            plan = self._build_rebalance_plan(pending, nav, realized_weights)
        except ValueError as exc:
            return RebalanceResult(
                orders=(),
                summary=_summary(nav, len(pending), 0, 0, GateOutcome.ERROR, 0.0),
                halt_reason=str(exc),
            )

        self._last_sleeve_weights = dict(plan.applied_sleeve_weights)
        sized_orders, prices = self._size_plan(plan.deltas, nav, period)
        executable_orders = _orders_for_fresh_refs(sized_orders, self._fresh_refs(period))
        total_notional = sum(abs(order.quantity) for order in executable_orders)

        self._record_period(nav, realized_weights, pending, prices)

        return RebalanceResult(
            orders=executable_orders,
            summary=_summary(
                nav,
                len(pending),
                len(sized_orders),
                len(executable_orders),
                GateOutcome.PASS,
                total_notional,
            ),
        )

    def _compute_sleeve_targets(
        self, period: CompletedRebalancePeriod
    ) -> dict[SleeveName, pd.DataFrame]:
        pending: dict[SleeveName, pd.DataFrame] = {}
        for sleeve in self._book.sleeves:
            bundle = self._sleeve_to_bundle.get(sleeve.name)
            if bundle is None:
                continue
            contract = bundle.contract
            sleeve_bars = self._bars_for_contract(contract, period)
            if sleeve_bars is None:
                continue
            arrays = {
                name: _combine_array_series(sleeve_bars, name)
                for name in contract.required_arrays
            }
            fx_series = self._fx_series_for(contract, next(iter(arrays.values())).index)
            if fx_series is None:
                continue
            pending[sleeve.name] = bundle.compute_weights(
                MarketDataBundle(arrays), fx_series=fx_series
            )
        return pending

    def _build_rebalance_plan(
        self,
        pending: dict[SleeveName, pd.DataFrame],
        nav: float,
        realized_weights: dict[InstrumentRef, float],
    ) -> RebalancePlan:
        return rebalance_plan(
            pending,
            self._book,
            realized_weights=realized_weights,
            realized_covariance=self._ledger.realized_covariance(
                self._positive_risk_sleeve_names()
            ),
            previous_sleeve_weights=self._last_sleeve_weights,
            realized_drawdown=self._ledger.current_drawdown(nav),
        )

    def _size_plan(
        self,
        deltas: tuple[WeightDelta, ...],
        nav: float,
        period: CompletedRebalancePeriod,
    ) -> tuple[tuple[OrderIntent, ...], dict[InstrumentRef, float]]:
        instrument_metas, fx_rates, prices = self._collect_sizing_params(period)
        orders = size_deltas(
            deltas,
            nav,
            instrument_metas=instrument_metas,
            fx_rates=fx_rates,
            prices=prices,
        )
        return orders, prices

    def _record_period(
        self,
        nav: float,
        realized_weights: Mapping[InstrumentRef, float],
        pending: Mapping[SleeveName, pd.DataFrame],
        prices: Mapping[InstrumentRef, float],
    ) -> None:
        self._ledger.record(
            nav=nav,
            realized_weights=dict(realized_weights),
            sleeve_targets=_sleeve_target_snapshot(pending),
            closes=dict(prices),
        )

    def _bars_for_contract(
        self,
        contract: DataContract,
        period: CompletedRebalancePeriod,
    ) -> dict[InstrumentRef, Sequence[MarketBar]] | None:
        needed = contract.lookback_bars + 1
        sleeve_bars: dict[InstrumentRef, Sequence[MarketBar]] = {}
        for ref in contract.refs:
            bars = self._lookback_window(ref, contract.timeframe, period, limit=needed)
            if len(bars) < needed:
                return None
            sleeve_bars[ref] = bars
        return sleeve_bars

    def _fresh_refs(self, period: CompletedRebalancePeriod) -> frozenset[InstrumentRef]:
        return frozenset(
            ref for ref in self._all_refs if self._has_bar_in_period(ref, period)
        )

    def _lookback_window(
        self,
        ref: InstrumentRef,
        timeframe: str,
        period: CompletedRebalancePeriod,
        *,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        return self._market_data.lookback_window(
            ref,
            self.instrument_id_for_ref(ref),
            timeframe,
            period=period.period,
            period_ns=period.period_ns,
            limit=limit,
        )

    def _has_bar_in_period(
        self, ref: InstrumentRef, period: CompletedRebalancePeriod
    ) -> bool:
        return self._market_data.has_bar_in_period(
            ref,
            self.instrument_id_for_ref(ref),
            self._timeframe_by_ref[ref],
            period=period.period,
            period_ns=period.period_ns,
        )

    def _collect_sizing_params(
        self,
        period: CompletedRebalancePeriod,
    ) -> tuple[dict[InstrumentRef, InstrumentSizing], dict[str, float], dict[InstrumentRef, float]]:
        instrument_metas: dict[InstrumentRef, InstrumentSizing] = {}
        prices: dict[InstrumentRef, float] = {}
        currencies: set[str] = set()

        for ref in self._all_refs:
            resolved_id = self.instrument_id_for_ref(ref)
            sizing = self._market_data.instrument_sizing(resolved_id)
            if sizing is None:
                continue
            quote_currency = self._reconcile_ref_currency(ref, sizing.currency)
            instrument_metas[ref] = InstrumentSizing(
                currency=quote_currency,
                size_increment=sizing.size_increment,
            )
            bars = self._lookback_window(ref, self._timeframe_by_ref[ref], period, limit=1)
            if bars:
                prices[ref] = float(bars[-1].close)
            currencies.add(quote_currency)

        fx_rates: dict[str, float] = {}
        for currency in currencies:
            rate = self._get_fx_rate(currency)
            if rate is not None:
                fx_rates[currency] = rate
        return instrument_metas, fx_rates, prices

    def _fx_series_for(
        self, contract: DataContract, index: pd.Index
    ) -> dict[str, pd.Series] | None:
        if not contract.required_fx_currencies:
            return {}
        series: dict[str, pd.Series] = {}
        for currency in contract.required_fx_currencies:
            rate = self._market_data.fx_rate(self._book.base_currency, currency)
            if rate is None:
                return None
            series[currency] = pd.Series(rate, index=index)
        return series

    def _get_fx_rate(self, target_currency: str) -> float | None:
        major = major_currency(target_currency)
        if major == self._book.base_currency:
            return 1.0
        return self._market_data.fx_rate(self._book.base_currency, major)

    def _positive_risk_sleeve_names(self) -> tuple[SleeveName, ...]:
        risk_shares = self._book.allocator_risk_shares()
        return tuple(
            sleeve.name for sleeve in self._book.sleeves if risk_shares[sleeve.name] > 0
        )


def _ref_sort_key(ref: InstrumentRef) -> tuple[int, str]:
    if isinstance(ref, ListedRef):
        return (0, ref.value)
    return (1, ref.value)


def _timeframe_by_ref(
    sleeve_to_bundle: Mapping[SleeveName, ExecutionBundle]
) -> dict[InstrumentRef, str]:
    timeframes: dict[InstrumentRef, str] = {}
    for bundle in sleeve_to_bundle.values():
        for ref in bundle.contract.refs:
            timeframes.setdefault(ref, bundle.contract.timeframe)
    return timeframes


_BAR_ARRAY_ACCESSORS: dict[str, Callable[[MarketBar], float]] = {
    "Open": lambda b: b.open,
    "High": lambda b: b.high,
    "Low": lambda b: b.low,
    "Close": lambda b: b.close,
    "Volume": lambda b: b.volume,
}


def _bars_to_array_series(
    bars: Sequence[MarketBar], ref: InstrumentRef, array_name: str
) -> pd.DataFrame:
    accessor = _BAR_ARRAY_ACCESSORS[array_name]
    index = pd.DatetimeIndex([bar.ts_event for bar in bars])
    values = [accessor(bar) for bar in bars]
    return pd.DataFrame({ref: values}, index=index)


def _combine_array_series(
    bars_by_ref: Mapping[InstrumentRef, Sequence[MarketBar]], array_name: str
) -> pd.DataFrame:
    frames = {
        ref: _bars_to_array_series(bars, ref, array_name)
        for ref, bars in bars_by_ref.items()
    }
    if len(frames) == 1:
        return next(iter(frames.values()))
    return pd.concat(frames.values(), axis=1)


def _orders_for_fresh_refs(
    orders: Sequence[OrderIntent], fresh_refs: frozenset[InstrumentRef]
) -> tuple[OrderIntent, ...]:
    return tuple(order for order in orders if order.ref in fresh_refs)


def _sleeve_target_snapshot(
    pending: Mapping[SleeveName, pd.DataFrame],
) -> dict[SleeveName, dict[InstrumentRef, float]]:
    return {
        name: {
            _column_ref(ref): float(weight)
            for ref, weight in target_df.iloc[-1].to_dict().items()
        }
        for name, target_df in pending.items()
    }


def _column_ref(column: object) -> InstrumentRef:
    if isinstance(column, ListedRef | FuturesRef):
        return column
    return ListedRef(str(column))


def _identity_currency(_ref: InstrumentRef, currency: str) -> str:
    return currency


def _summary(
    nav: float,
    num_sleeves: int,
    num_targets: int,
    num_orders: int,
    gate_outcome: GateOutcome,
    total_notional: float,
) -> RebalanceSummary:
    return RebalanceSummary(
        nav=nav,
        num_sleeves=num_sleeves,
        num_targets=num_targets,
        num_orders=num_orders,
        gate_outcome=gate_outcome,
        total_notional=total_notional,
    )
