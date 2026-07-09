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

from aegis_runtime import (
    DataContract,
    ExecutionBundle,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.currency import (
    CurrencyConversion,
    build_currency_conversion_from_codes,
)

from aegis_trader.bundles.bands import BundleBands, InstrumentBandError, build_instrument_bands
from aegis_trader.bundles.provenance import CapProvenanceError, check_cap_provenance
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import check_account_integrity
from aegis_trader.domain.rebalancer import (
    RebalancePlan,
    rebalance_plan,
    validate_executable_plan,
)
from aegis_trader.domain.roll import RollEvent
from aegis_trader.domain.sizing import InstrumentSizing, SizedOrder, size_deltas
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain import startup as _startup
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


@dataclass(frozen=True)
class CompletedRebalancePeriod:
    """Completed rebalance-period coordinates for Cache-backed bar reads."""

    period: int
    period_ns: int


@dataclass(frozen=True)
class SleeveComputeFailure:
    """One sleeve's failed weight computation, surfaced instead of raised."""

    sleeve: SleeveName
    reason: str


@dataclass(frozen=True)
class RebalanceResult:
    """Plain output of one rebalance period."""

    orders: tuple[OrderIntent, ...]
    summary: RebalanceSummary
    halt_reason: str | None = None
    sleeve_failures: tuple[SleeveComputeFailure, ...] = ()


DROP_POLICY_LOOKBACK_SLACK = 256


class MissingIndexAlignmentError(ValueError):
    """A sleeve's bar panel violates the bundle contract's missing-index policy."""


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
    ) -> None:
        self._book_state = book_state
        self._market_data = market_data
        self._book = book
        self._sleeve_to_bundle = sleeve_to_bundle
        self._ledger = ledger
        self._bundle_bands: BundleBands | None = None
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
    def last_sleeve_weights(self) -> dict[SleeveName, float]:
        """Last allocator-applied sleeve multipliers, for evidence/backtest seams."""
        return dict(self._last_sleeve_weights)

    @property
    def observation_count(self) -> int:
        """Number of completed rebalance observations in the owned ledger."""
        return self._ledger.observation_count

    def realized_book_skew(
        self,
        weights: Mapping[SleeveName, float],
        names: Sequence[SleeveName],
    ) -> float | None:
        """Realized skew query over the owned ledger."""
        return self._ledger.realized_book_skew(weights, names)

    def attribution(self, budgets: Mapping[SleeveName, float]) -> dict[SleeveName, float]:
        """Per-sleeve P&L attribution query over the owned ledger."""
        return self._ledger.attribution(budgets)

    def apply_roll(self, event: RollEvent) -> None:
        """Carry ledger closes into the Roll's new continuous basis."""
        self._ledger.rebase_closes({event.continuous_id: event.rebasing})

    def startup_check(self) -> _startup.StartupResult:
        """Run startup gates and return the decision as a value object."""
        band_result = self._band_ownership_startup_result()
        if band_result is not None:
            return band_result
        cap_result = self._cap_provenance_startup_result()
        if cap_result is not None:
            return cap_result
        return self._account_integrity_startup_result()

    def _band_ownership_startup_result(self) -> _startup.StartupResult | None:
        try:
            self._bundle_bands = build_instrument_bands(self._sleeve_to_bundle)
        except InstrumentBandError as exc:
            return _startup.StartupResult(
                trading_enabled=False,
                halt_gate=_startup.StartupGate.BAND_OWNERSHIP,
                halt_reason=str(exc),
            )
        return None

    def _cap_provenance_startup_result(self) -> _startup.StartupResult | None:
        try:
            check_cap_provenance(self._book, self._sleeve_to_bundle)
        except CapProvenanceError as exc:
            return _startup.StartupResult(
                trading_enabled=False,
                halt_gate=_startup.StartupGate.CAP_PROVENANCE,
                halt_reason=str(exc),
            )
        return None

    def _account_integrity_startup_result(self) -> _startup.StartupResult:
        try:
            nav = self._book_state.nav()
            cash = self._book_state.cash()
        except Exception as exc:
            return _startup.StartupResult(
                trading_enabled=False,
                halt_gate=_startup.StartupGate.ACCOUNT_INTEGRITY,
                halt_reason=f"Failed to query book state for integrity check: {exc}",
            )

        report = check_account_integrity(
            nav=nav,
            cash=cash,
            cache_healthy=self._book_state.is_cache_healthy(),
        )
        if not report.healthy:
            return _startup.StartupResult(
                trading_enabled=False,
                halt_gate=_startup.StartupGate.ACCOUNT_INTEGRITY,
                halt_reason=report.reason or "Unknown integrity failure",
                nav=nav,
                cash=cash,
            )
        return _startup.StartupResult(trading_enabled=True, nav=nav, cash=cash)

    def rebalance_period(self, period: CompletedRebalancePeriod) -> RebalanceResult:
        """Run one completed-period rebalance and return orders plus summary."""
        pending, sleeve_failures = self._compute_sleeve_targets(period)
        nav = self._book_state.nav()
        realized_weights = self._book_state.realized_weights()
        if not pending:
            try:
                validate_executable_plan(realized_weights, (), self._book)
            except ValueError as exc:
                return _gate_error_result(
                    nav=nav,
                    num_sleeves=0,
                    num_targets=0,
                    reason=str(exc),
                    sleeve_failures=sleeve_failures,
                )
            return RebalanceResult(
                orders=(),
                summary=_summary(nav, 0, 0, 0, GateOutcome.PASS, 0.0),
                sleeve_failures=sleeve_failures,
            )

        try:
            plan = self._build_rebalance_plan(pending, nav, realized_weights)
        except ValueError as exc:
            return _gate_error_result(
                nav=nav,
                num_sleeves=len(pending),
                num_targets=0,
                reason=str(exc),
                sleeve_failures=sleeve_failures,
            )

        sized_orders, prices = self._size_plan(plan.deltas, nav, period)
        executable_sized_orders = _sized_orders_for_fresh_instruments(
            sized_orders,
            self._fresh_instrument_ids(period),
        )
        try:
            validate_executable_plan(
                realized_weights,
                tuple(sized.projected_delta for sized in executable_sized_orders),
                self._book,
            )
        except ValueError as exc:
            return _gate_error_result(
                nav=nav,
                num_sleeves=len(pending),
                num_targets=len(sized_orders),
                reason=str(exc),
                sleeve_failures=sleeve_failures,
            )

        self._last_sleeve_weights = dict(plan.applied_sleeve_weights)
        order_intents = tuple(sized.intent for sized in executable_sized_orders)
        total_notional = sum(abs(order.quantity) for order in order_intents)

        self._record_period(nav, realized_weights, pending, prices)

        return RebalanceResult(
            orders=order_intents,
            summary=_summary(
                nav,
                len(pending),
                len(sized_orders),
                len(order_intents),
                GateOutcome.PASS,
                total_notional,
            ),
            sleeve_failures=sleeve_failures,
        )

    def _compute_sleeve_targets(
        self, period: CompletedRebalancePeriod
    ) -> tuple[dict[SleeveName, pd.DataFrame], tuple[SleeveComputeFailure, ...]]:
        """Each sleeve's targets, computed in isolation: a sleeve whose compute raises
        is excluded (it holds this period) and surfaced as a failure — one bad sleeve
        must never abort the other sleeves' rebalance (aegis-rd-hd54)."""
        pending: dict[SleeveName, pd.DataFrame] = {}
        failures: list[SleeveComputeFailure] = []
        for sleeve in self._book.sleeves:
            bundle = self._sleeve_to_bundle.get(sleeve.name)
            if bundle is None:
                continue
            try:
                targets = self._sleeve_targets(bundle, period)
            except Exception as exc:  # noqa: BLE001 — fail closed per sleeve, not per book
                failures.append(
                    SleeveComputeFailure(
                        sleeve=sleeve.name,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            if targets is None:
                continue
            pending[sleeve.name] = targets
        return pending, tuple(failures)

    def _sleeve_targets(
        self, bundle: ExecutionBundle, period: CompletedRebalancePeriod
    ) -> pd.DataFrame | None:
        contract = bundle.contract
        sleeve_bars = self._bars_for_contract(contract, period)
        if sleeve_bars is None:
            return None
        arrays = {
            name: _combine_array_series(sleeve_bars, name)
            for name in contract.required_arrays
        }
        # The pipeline resolves the period's market facts; the bundle owns the
        # native -> base transformation, so the conversion is applied exactly once
        # (and roll probes can perturb native prices before it).
        conversion = self._currency_conversion(contract, period)
        return bundle.compute_weights(
            MarketDataBundle(arrays),
            currency_conversion=conversion,
        )

    def _currency_conversion(
        self, contract: DataContract, period: CompletedRebalancePeriod
    ) -> CurrencyConversion | None:
        """The contract's ``exchange:``-leg conversion to its base currency.

        Research validated the sleeve on base-currency-converted panels; the
        trader computes on the same view (aegis-rd-reyj). Any gap — a leg that
        is not a cached FX pair, missing FX bars, an unresolvable tradeable
        currency — raises, so the sleeve fails closed instead of silently
        computing on native prices.
        """
        if not contract.exchange:
            return None
        needed = contract.lookback_bars + 1
        fx_close: dict[InstrumentId, pd.Series] = {}
        pair_currencies: dict[InstrumentId, tuple[str, str]] = {}
        for fx_id in contract.exchange:
            pair = self._market_data.currency_pair(fx_id)
            if pair is None:
                raise ValueError(
                    f"conversion leg {fx_id.value} is not a cash FX pair in the cache"
                )
            bars = self._lookback_window(
                fx_id,
                contract.timeframe,
                period,
                limit=needed + DROP_POLICY_LOOKBACK_SLACK,
            )
            if not bars:
                raise ValueError(f"no FX bars for conversion leg {fx_id.value}")
            pair_currencies[fx_id] = pair
            fx_close[fx_id] = pd.Series(
                [bar.close for bar in bars],
                index=pd.DatetimeIndex([bar.ts_event for bar in bars]),
            )
        currency_by_instrument_id: dict[InstrumentId, str] = {}
        for instrument_id in self._contract_target_ids(contract):
            sizing = self._market_data.instrument_sizing(instrument_id)
            if sizing is None:
                raise ValueError(
                    f"no cached instrument for {instrument_id.value}; its quote "
                    "currency is required for base-currency conversion"
                )
            currency_by_instrument_id[instrument_id] = sizing.currency
        return build_currency_conversion_from_codes(
            currency_by_instrument_id=currency_by_instrument_id,
            pair_currencies=pair_currencies,
            fx_close=fx_close,
            base_currency=contract.base_currency,
        )

    def _build_rebalance_plan(
        self,
        pending: dict[SleeveName, pd.DataFrame],
        _nav: float,
        realized_weights: dict[InstrumentId, float],
    ) -> RebalancePlan:
        bundle_bands = self._require_bundle_bands()
        return rebalance_plan(
            pending,
            self._book,
            realized_weights=realized_weights,
            instrument_bands=bundle_bands.bands,
            band_owners=bundle_bands.owner_by_instrument,
            realized_covariance=self._ledger.realized_covariance(
                self._positive_risk_sleeve_names()
            ),
            previous_sleeve_weights=self._last_sleeve_weights,
            realized_drawdown=self._ledger.current_drawdown(_nav),
        )

    def _require_bundle_bands(self) -> BundleBands:
        if self._bundle_bands is None:
            raise RuntimeError("instrument bands queried before startup_check built them")
        return self._bundle_bands

    def _size_plan(
        self,
        deltas: tuple[WeightDelta, ...],
        nav: float,
        period: CompletedRebalancePeriod,
    ) -> tuple[tuple[SizedOrder, ...], dict[InstrumentId, float]]:
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
        """A contract's full rebalance-target universe, as declared by the bundle."""
        target_ids = frozenset(
            (*contract.native_instrument_ids, *contract.continuous_instrument_ids)
        )
        return tuple(
            instrument_id
            for instrument_id in contract.instrument_ids
            if instrument_id in target_ids
        )

    def _bars_for_contract(
        self,
        contract: DataContract,
        period: CompletedRebalancePeriod,
    ) -> dict[InstrumentId, Sequence[MarketBar]] | None:
        needed = contract.lookback_bars + 1
        target_ids = self._contract_target_ids(contract)
        limit = _lookback_limit(contract, target_count=len(target_ids), needed=needed)
        sleeve_bars: dict[InstrumentId, Sequence[MarketBar]] = {}
        for instrument_id in target_ids:
            bars = self._lookback_window(
                instrument_id,
                contract.timeframe,
                period,
                limit=limit,
            )
            if len(bars) < needed:
                return None
            sleeve_bars[instrument_id] = bars
        if contract.missing_index is MissingIndexPolicy.DROP:
            return _last_common_bars(sleeve_bars, needed)
        if contract.missing_index is MissingIndexPolicy.RAISE and not _bars_share_timestamps(
            sleeve_bars
        ):
            raise MissingIndexAlignmentError(
                "missing_index='raise' bundle contract received misaligned bar timestamps"
            )
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


def _lookback_limit(
    contract: DataContract, *, target_count: int, needed: int
) -> int:
    if contract.missing_index is not MissingIndexPolicy.DROP or target_count <= 1:
        return needed
    return needed + DROP_POLICY_LOOKBACK_SLACK


def _last_common_bars(
    bars_by_instrument_id: Mapping[InstrumentId, Sequence[MarketBar]], needed: int
) -> dict[InstrumentId, Sequence[MarketBar]] | None:
    if len(bars_by_instrument_id) <= 1:
        return {
            instrument_id: tuple(bars[-needed:])
            for instrument_id, bars in bars_by_instrument_id.items()
        }
    timestamp_sets = [
        {bar.ts_event for bar in bars} for bars in bars_by_instrument_id.values()
    ]
    common_timestamps = sorted(set.intersection(*timestamp_sets))
    if len(common_timestamps) < needed:
        return None
    selected_timestamps = tuple(common_timestamps[-needed:])
    selected: dict[InstrumentId, Sequence[MarketBar]] = {}
    for instrument_id, bars in bars_by_instrument_id.items():
        by_timestamp = {bar.ts_event: bar for bar in bars}
        selected[instrument_id] = tuple(
            by_timestamp[timestamp] for timestamp in selected_timestamps
        )
    return selected


def _bars_share_timestamps(
    bars_by_instrument_id: Mapping[InstrumentId, Sequence[MarketBar]],
) -> bool:
    expected: tuple[int, ...] | None = None
    for bars in bars_by_instrument_id.values():
        timestamps = tuple(bar.ts_event for bar in bars)
        if expected is None:
            expected = timestamps
            continue
        if timestamps != expected:
            return False
    return True


def _sized_orders_for_fresh_instruments(
    sized_orders: Sequence[SizedOrder], fresh_instrument_ids: frozenset[InstrumentId]
) -> tuple[SizedOrder, ...]:
    return tuple(
        sized
        for sized in sized_orders
        if sized.intent.instrument_id in fresh_instrument_ids
    )


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


def _gate_error_result(
    *,
    nav: float,
    num_sleeves: int,
    num_targets: int,
    reason: str,
    sleeve_failures: tuple[SleeveComputeFailure, ...],
) -> RebalanceResult:
    return RebalanceResult(
        orders=(),
        summary=_summary(
            nav,
            num_sleeves,
            num_targets,
            0,
            GateOutcome.ERROR,
            0.0,
        ),
        halt_reason=reason,
        sleeve_failures=sleeve_failures,
    )
