"""Strategy-free per-period rebalance orchestration over injected ports.

The pipeline owns the rebalance path: build each sleeve's runtime market bundle
from a completed-period bar snapshot, run the sleeve Execution Bundles, net
through the rebalancer, size into OrderIntents, record the SleeveLedger, and
return value objects for the Strategy to log and submit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import DataContract, ExecutionBundle, MarketDataBundle

from aegis_trader.bundles.provenance import CapProvenanceError, check_cap_provenance
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import check_account_integrity
from aegis_trader.domain.rebalancer import RebalancePlan, rebalance_plan
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import OrderIntent, SleeveName, WeightDelta

if TYPE_CHECKING:
    from aegis_trader.data.market_data import MarketDataPort
    from aegis_trader.portfolio import BookStatePort


class GateOutcome(str, Enum):
    """Outcome of the cap/band gate during a rebalance."""

    PASS = "pass"
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


class RebalancePipeline:
    """Per-period rebalance orchestrator behind a value-object API.

    Constructor injection keeps the Nautilus lifecycle at the edge: the Strategy
    supplies cache-backed ports.  The pipeline works only with native
    InstrumentIds declared by the bundle contracts, plain market bars, and
    value-object requests.
    """

    def __init__(
        self,
        *,
        book_state: BookStatePort,
        market_data: MarketDataPort,
        book: BookConfig,
        sleeve_to_bundle: Mapping[SleeveName, ExecutionBundle],
        ledger: SleeveLedger,
        continuous_ids_by_root: Mapping[str, InstrumentId] | None = None,
    ) -> None:
        self._book_state = book_state
        self._market_data = market_data
        self._book = book
        self._sleeve_to_bundle = sleeve_to_bundle
        self._ledger = ledger
        # Continuous roots are first-class rebalance targets (mirroring research's tradeable set =
        # natives + continuous roots): a sleeve's bare root maps here to its synthetic continuous id.
        self._continuous_ids_by_root = dict(continuous_ids_by_root or {})
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        timeframe_by_instrument_id: dict[InstrumentId, str] = {}
        for bundle in self._sleeve_to_bundle.values():
            for instrument_id in self._contract_target_ids(bundle.contract):
                timeframe_by_instrument_id.setdefault(
                    instrument_id, bundle.contract.timeframe
                )
        self._all_instrument_ids = frozenset(timeframe_by_instrument_id)
        self._timeframe_by_instrument_id = timeframe_by_instrument_id

    @property
    def sleeve_ledger(self) -> SleeveLedger:
        """Cross-period analytics ledger owned by the pipeline."""
        return self._ledger

    @property
    def last_sleeve_weights(self) -> dict[SleeveName, float]:
        """Last allocator-applied sleeve multipliers, for evidence/backtest seams."""
        return dict(self._last_sleeve_weights)

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
        executable_orders = _orders_for_fresh_instruments(
            sized_orders,
            self._fresh_instrument_ids(period),
        )
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
            pending[sleeve.name] = bundle.compute_weights(MarketDataBundle(arrays))
        return pending

    def _build_rebalance_plan(
        self,
        pending: dict[SleeveName, pd.DataFrame],
        _nav: float,
        realized_weights: dict[InstrumentId, float],
    ) -> RebalancePlan:
        return rebalance_plan(
            pending,
            self._book,
            realized_weights=realized_weights,
            realized_covariance=self._ledger.realized_covariance(
                self._positive_risk_sleeve_names()
            ),
            previous_sleeve_weights=self._last_sleeve_weights,
            realized_drawdown=self._ledger.current_drawdown(_nav),
        )

    def _size_plan(
        self,
        deltas: tuple[WeightDelta, ...],
        nav: float,
        period: CompletedRebalancePeriod,
    ) -> tuple[tuple[OrderIntent, ...], dict[InstrumentId, float]]:
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
        realized_weights: Mapping[InstrumentId, float],
        pending: Mapping[SleeveName, pd.DataFrame],
        prices: Mapping[InstrumentId, float],
    ) -> None:
        self._ledger.record(
            nav=nav,
            realized_weights=dict(realized_weights),
            sleeve_targets=_sleeve_target_snapshot(pending),
            closes=dict(prices),
        )

    def _contract_target_ids(self, contract: DataContract) -> tuple[InstrumentId, ...]:
        """A contract's full rebalance-target universe: its native instruments plus the synthetic
        continuous-root id for each declared root (the continuous series is read by that id)."""
        continuous = tuple(
            self._continuous_ids_by_root[root]
            for root in contract.futures
            if root in self._continuous_ids_by_root
        )
        return (*contract.instrument_ids, *continuous)

    def _bars_for_contract(
        self,
        contract: DataContract,
        period: CompletedRebalancePeriod,
    ) -> dict[InstrumentId, Sequence[MarketBar]] | None:
        needed = contract.lookback_bars + 1
        sleeve_bars: dict[InstrumentId, Sequence[MarketBar]] = {}
        for instrument_id in self._contract_target_ids(contract):
            bars = self._lookback_window(
                instrument_id,
                contract.timeframe,
                period,
                limit=needed,
            )
            if len(bars) < needed:
                return None
            sleeve_bars[instrument_id] = bars
        return sleeve_bars

    def _fresh_instrument_ids(self, period: CompletedRebalancePeriod) -> frozenset[InstrumentId]:
        return frozenset(
            instrument_id
            for instrument_id in self._all_instrument_ids
            if self._has_bar_in_period(instrument_id, period)
        )

    def _lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        period: CompletedRebalancePeriod,
        *,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        return self._market_data.lookback_window(
            instrument_id,
            timeframe,
            period=period.period,
            period_ns=period.period_ns,
            limit=limit,
        )

    def _has_bar_in_period(
        self, instrument_id: InstrumentId, period: CompletedRebalancePeriod
    ) -> bool:
        return self._market_data.has_bar_in_period(
            instrument_id,
            self._timeframe_by_instrument_id[instrument_id],
            period=period.period,
            period_ns=period.period_ns,
        )

    def _collect_sizing_params(
        self,
        period: CompletedRebalancePeriod,
    ) -> tuple[dict[InstrumentId, InstrumentSizing], dict[str, float], dict[InstrumentId, float]]:
        instrument_metas: dict[InstrumentId, InstrumentSizing] = {}
        prices: dict[InstrumentId, float] = {}
        currencies: set[str] = set()

        for instrument_id in self._all_instrument_ids:
            sizing = self._market_data.instrument_sizing(instrument_id)
            if sizing is None:
                continue
            instrument_metas[instrument_id] = sizing
            bars = self._lookback_window(
                instrument_id,
                self._timeframe_by_instrument_id[instrument_id],
                period,
                limit=1,
            )
            if bars:
                prices[instrument_id] = float(bars[-1].close)
            currencies.add(sizing.currency)

        fx_rates: dict[str, float] = {}
        for currency in currencies:
            rate = self._get_fx_rate(currency)
            if rate is not None:
                fx_rates[currency] = rate
        return instrument_metas, fx_rates, prices

    def _get_fx_rate(self, target_currency: str) -> float | None:
        if target_currency == self._book.base_currency:
            return 1.0
        return self._market_data.fx_rate(self._book.base_currency, target_currency)

    def _positive_risk_sleeve_names(self) -> tuple[SleeveName, ...]:
        risk_shares = self._book.allocator_risk_shares()
        return tuple(
            sleeve.name for sleeve in self._book.sleeves if risk_shares[sleeve.name] > 0
        )


_BAR_ARRAY_ACCESSORS: dict[str, Callable[[MarketBar], float]] = {
    "Open": lambda b: b.open,
    "High": lambda b: b.high,
    "Low": lambda b: b.low,
    "Close": lambda b: b.close,
    "Volume": lambda b: b.volume,
}


def _bars_to_array_series(
    bars: Sequence[MarketBar], instrument_id: InstrumentId, array_name: str
) -> pd.DataFrame:
    accessor = _BAR_ARRAY_ACCESSORS[array_name]
    index = pd.DatetimeIndex([bar.ts_event for bar in bars])
    values = [accessor(bar) for bar in bars]
    return pd.DataFrame({instrument_id: values}, index=index)


def _combine_array_series(
    bars_by_instrument_id: Mapping[InstrumentId, Sequence[MarketBar]], array_name: str
) -> pd.DataFrame:
    frames = {
        instrument_id: _bars_to_array_series(bars, instrument_id, array_name)
        for instrument_id, bars in bars_by_instrument_id.items()
    }
    if len(frames) == 1:
        return next(iter(frames.values()))
    return pd.concat(frames.values(), axis=1)


def _orders_for_fresh_instruments(
    orders: Sequence[OrderIntent], fresh_instrument_ids: frozenset[InstrumentId]
) -> tuple[OrderIntent, ...]:
    return tuple(order for order in orders if order.instrument_id in fresh_instrument_ids)


def _sleeve_target_snapshot(
    pending: Mapping[SleeveName, pd.DataFrame],
) -> dict[SleeveName, dict[InstrumentId, float]]:
    return {
        name: {
            _column_instrument_id(instrument_id): float(weight)
            for instrument_id, weight in target_df.iloc[-1].to_dict().items()
        }
        for name, target_df in pending.items()
    }


def _column_instrument_id(column: object) -> InstrumentId:
    if isinstance(column, InstrumentId):
        return column
    raise ValueError(f"target weight columns must be InstrumentId values; got {column!r}")


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
