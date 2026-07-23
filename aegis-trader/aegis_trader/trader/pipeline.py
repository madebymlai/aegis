"""Strategy-free per-period rebalance orchestration over injected ports.

The pipeline owns the rebalance path: build each sleeve's runtime market bundle
from a completed-period bar snapshot, run the sleeve Execution Bundles, net
through the rebalancer, size into OrderIntents, record the SleeveLedger, and
return value objects for the Strategy to log and submit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
from aegis_runtime.exposure_validation import NetExposureBreach

from aegis_trader.bundles.book import AssembledBook
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.integrity import check_account_integrity
from aegis_trader.domain.roll import RollEvent
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.sleeve_ledger import BookObservation, SleeveLedger
from aegis_trader.domain import startup as _startup
from aegis_trader.domain.types import OrderIntent, SleeveName
from aegis_trader.trader._rebalancer import (
    PerNameExposureBreach,
    RebalancePlan,
    rebalance_plan,
)
from aegis_trader.trader.sleeve_arrays import SleeveArrayGrid, SleeveArrays

if TYPE_CHECKING:
    from aegis_trader.data.market_data import MarketDataPort
    from aegis_trader.portfolio import BookStatePort


class GateOutcome(str, Enum):
    """Outcome of the cap/band gate during a rebalance."""

    PASS = "pass"
    ERROR = "error"


class HaltCause(str, Enum):
    """The behaviorally distinct halt families of a failed rebalance plan.

    The closed vocabulary consumers branch on; ``halt_reason`` carries the
    human-readable detail.  One value per contract, not per raise site: every
    per-name breach — unfixable target, unremediable position, projected
    sweep — is the one fail-closed per-name contract (ADR-0002).
    """

    PER_NAME_CAP_BREACH = "per_name_cap_breach"
    NET_CAP_BREACH = "net_cap_breach"
    PLANNING_FAILED = "planning_failed"


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
class DueSleeve:
    """One Sleeve due for recomputation on its own completed period."""

    sleeve: SleeveName
    period: CompletedRebalancePeriod


@dataclass(frozen=True)
class RebalanceRequest:
    """One Book re-net: the Sleeves whose periods completed, with coordinates.

    Only the listed Sleeves recompute; every other Sleeve holds its latest
    valid target, and the whole retained Book is allocated, gated, and netted.
    ``timestamp_ns`` is the integer UTC event time driving the re-net (the
    triggering bar), stamping the Book observation the ledger records.
    """

    due: tuple[DueSleeve, ...]
    timestamp_ns: int


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
    halt_cause: HaltCause | None = None
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
        book: AssembledBook,
        ledger: SleeveLedger,
        arrays: SleeveArrays,
    ) -> None:
        self._book_state = book_state
        self._market_data = market_data
        self._book = book.config
        self._sleeves = book.sleeves
        self._ledger = ledger
        self._arrays = arrays
        self._bundle_bands = book.bands
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        # The latest valid target frame per Sleeve: due computations replace an
        # entry; non-due, warming, stale, or failed Sleeves retain theirs.
        self._retained_targets: dict[SleeveName, pd.DataFrame] = {}
        # The most recent completed period seen per Sleeve — a market-time fact
        # (recorded whether or not the compute succeeded) that scopes freshness
        # and sizing reads for that Sleeve's instruments between its dues.
        self._last_period_by_sleeve: dict[SleeveName, CompletedRebalancePeriod] = {}
        timeframe_by_instrument_id: dict[InstrumentId, str] = {}
        consumer_by_instrument_id: dict[InstrumentId, SleeveName] = {}
        for sleeve_name, bundle in self._sleeves.items():
            for instrument_id in bundle.contract.instrument_ids:
                timeframe_by_instrument_id.setdefault(
                    instrument_id, bundle.contract.timeframe
                )
                consumer_by_instrument_id.setdefault(instrument_id, sleeve_name)
        self._all_instrument_ids = frozenset(timeframe_by_instrument_id)
        self._timeframe_by_instrument_id = timeframe_by_instrument_id
        self._consumer_by_instrument_id = consumer_by_instrument_id

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

    def attribution(
        self, budgets: Mapping[SleeveName, float]
    ) -> dict[SleeveName, float]:
        """Per-sleeve P&L attribution query over the owned ledger."""
        return self._ledger.attribution(budgets)

    def apply_roll(self, event: RollEvent) -> None:
        """Carry ledger closes into the Roll's new continuous basis."""
        self._ledger.rebase_closes({event.continuous_id: event.rebasing})

    def startup_check(self) -> _startup.StartupResult:
        """Run startup gates and return the decision as a value object."""
        return self._account_integrity_startup_result()

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

    def rebalance(self, request: RebalanceRequest) -> RebalanceResult:
        """Recompute the due Sleeves, then allocate, gate, and net the full
        retained Book into one order set.

        The Book observation is recorded before planning, so the covariance
        the allocator queries already excludes the day this event opened —
        risk inputs use only completed UTC days (aegis-rd-9qkr.7).
        """
        sleeve_failures = self._compute_due_targets(request)
        nav = self._book_state.nav()
        realized_weights = self._book_state.realized_weights()
        instrument_metas, fx_rates, prices = self._collect_sizing_params()
        self._record_observation(request.timestamp_ns, nav, realized_weights, prices)

        pending = dict(self._retained_targets)
        if not pending:
            return RebalanceResult(
                orders=(),
                summary=_summary(nav, 0, 0, 0, GateOutcome.PASS, 0.0),
                sleeve_failures=sleeve_failures,
            )

        try:
            plan = self._build_rebalance_plan(pending, nav, realized_weights)
        except ValueError as exc:
            return RebalanceResult(
                orders=(),
                summary=_summary(nav, len(pending), 0, 0, GateOutcome.ERROR, 0.0),
                halt_reason=str(exc),
                halt_cause=_halt_cause(exc),
                sleeve_failures=sleeve_failures,
            )

        sized_orders = size_deltas(
            plan.deltas,
            nav,
            instrument_metas=instrument_metas,
            fx_rates=fx_rates,
            prices=prices,
        )
        executable_orders = _orders_for_fresh_instruments(
            sized_orders,
            self._fresh_instrument_ids(),
        )

        self._last_sleeve_weights = dict(plan.applied_sleeve_weights)
        total_notional = sum(abs(order.quantity) for order in executable_orders)

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
            sleeve_failures=sleeve_failures,
        )

    def record_market_observation(
        self, timestamp_ns: int, marks: Mapping[InstrumentId, float]
    ) -> None:
        """Record a timestamped full-Book observation for an advancing stream.

        Called whenever a relevant subscribed stream advances, whether or not
        any Sleeve is due — retained Sleeves stay marked independently of
        recomputation.  The pipeline records facts only; day bucketing,
        compounding, and annualization belong to the ledger.
        """
        self._record_observation(
            timestamp_ns,
            self._book_state.nav(),
            self._book_state.realized_weights(),
            marks,
        )

    def recover_market(
        self,
        request: RebalanceRequest,
        marks: Mapping[InstrumentId, float],
    ) -> tuple[SleeveComputeFailure, ...]:
        """Advance market-derived state without reconstructing broker history."""
        self._record_observation(
            request.timestamp_ns,
            1.0,
            {},
            marks,
        )
        failures = self._compute_due_targets(request)
        if request.due:
            _instrument_metas, _fx_rates, completed_period_marks = (
                self._collect_sizing_params()
            )
            self._record_observation(
                request.timestamp_ns + 1,
                1.0,
                {},
                completed_period_marks,
            )
        return failures

    def _record_observation(
        self,
        timestamp_ns: int,
        nav: float,
        realized_weights: Mapping[InstrumentId, float],
        marks: Mapping[InstrumentId, float],
    ) -> None:
        self._ledger.record(
            BookObservation(
                timestamp_ns=timestamp_ns,
                nav=nav,
                realized_weights=dict(realized_weights),
                sleeve_targets=_sleeve_target_snapshot(self._retained_targets),
                marks=dict(marks),
            )
        )

    def _compute_due_targets(
        self, request: RebalanceRequest
    ) -> tuple[SleeveComputeFailure, ...]:
        """Each due Sleeve's targets, computed in isolation on its own period.

        A successful compute replaces the Sleeve's retained target; a compute
        that raises is surfaced as a failure and the Sleeve holds its previous
        valid target — one bad sleeve must never abort the other sleeves'
        rebalance (aegis-rd-hd54).  A warming/stale Sleeve (no bars) holds
        silently.  Non-due Sleeves are not invoked at all.
        """
        period_by_sleeve = {due.sleeve: due.period for due in request.due}
        failures: list[SleeveComputeFailure] = []
        for sleeve in self._book.sleeves:
            period = period_by_sleeve.get(sleeve.name)
            if period is None:
                continue
            bundle = self._sleeves.get(sleeve.name)
            if bundle is None:
                continue
            self._last_period_by_sleeve[sleeve.name] = period
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
            self._retained_targets[sleeve.name] = targets
        return tuple(failures)

    def _sleeve_targets(
        self, bundle: ExecutionBundle, period: CompletedRebalancePeriod
    ) -> pd.DataFrame | None:
        contract = bundle.contract
        sleeve_bars = self._bars_for_contract(contract, period)
        if sleeve_bars is None:
            return None
        grid = SleeveArrayGrid.from_bars(contract, sleeve_bars)
        self._arrays.ensure(grid.need)
        arrays = self._arrays.project(grid)
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
        for instrument_id in contract.instrument_ids:
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
        return rebalance_plan(
            pending,
            self._book,
            realized_weights=realized_weights,
            instrument_bands=self._bundle_bands.bands,
            band_owners=self._bundle_bands.owner_by_instrument,
            realized_covariance=self._ledger.realized_covariance(
                self._positive_risk_sleeve_names()
            ),
            previous_sleeve_weights=self._last_sleeve_weights,
            realized_drawdown=self._ledger.current_drawdown(_nav),
        )

    def _bars_for_contract(
        self,
        contract: DataContract,
        period: CompletedRebalancePeriod,
    ) -> dict[InstrumentId, Sequence[MarketBar]] | None:
        needed = contract.lookback_bars + 1
        target_ids = contract.instrument_ids
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
        if (
            contract.missing_index is MissingIndexPolicy.RAISE
            and not _bars_share_timestamps(sleeve_bars)
        ):
            raise MissingIndexAlignmentError(
                "missing_index='raise' bundle contract received misaligned bar timestamps"
            )
        return sleeve_bars

    def _fresh_instrument_ids(self) -> frozenset[InstrumentId]:
        return frozenset(
            instrument_id
            for instrument_id in self._all_instrument_ids
            if self._has_bar_in_instrument_period(instrument_id)
        )

    def _instrument_period(
        self, instrument_id: InstrumentId
    ) -> CompletedRebalancePeriod | None:
        """The completed period that scopes reads for *instrument_id*: the most
        recent period seen by its consuming Sleeve, or ``None`` before that
        Sleeve's first due."""
        consumer = self._consumer_by_instrument_id.get(instrument_id)
        if consumer is None:
            return None
        return self._last_period_by_sleeve.get(consumer)

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

    def _has_bar_in_instrument_period(self, instrument_id: InstrumentId) -> bool:
        period = self._instrument_period(instrument_id)
        if period is None:
            return False
        return self._market_data.has_bar_in_period(
            instrument_id,
            self._timeframe_by_instrument_id[instrument_id],
            period=period.period,
            period_ns=period.period_ns,
        )

    def _collect_sizing_params(
        self,
    ) -> tuple[
        dict[InstrumentId, InstrumentSizing],
        dict[str, float],
        dict[InstrumentId, float],
    ]:
        instrument_metas: dict[InstrumentId, InstrumentSizing] = {}
        prices: dict[InstrumentId, float] = {}
        currencies: set[str] = set()

        for instrument_id in self._all_instrument_ids:
            sizing = self._market_data.instrument_sizing(instrument_id)
            if sizing is None:
                continue
            instrument_metas[instrument_id] = sizing
            period = self._instrument_period(instrument_id)
            bars = (
                ()
                if period is None
                else self._lookback_window(
                    instrument_id,
                    self._timeframe_by_instrument_id[instrument_id],
                    period,
                    limit=1,
                )
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


def _lookback_limit(contract: DataContract, *, target_count: int, needed: int) -> int:
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


def _orders_for_fresh_instruments(
    orders: Sequence[OrderIntent], fresh_instrument_ids: frozenset[InstrumentId]
) -> tuple[OrderIntent, ...]:
    return tuple(
        order for order in orders if order.instrument_id in fresh_instrument_ids
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
    raise ValueError(
        f"target weight columns must be InstrumentId values; got {column!r}"
    )


def _halt_cause(exc: ValueError) -> HaltCause:
    if isinstance(exc, PerNameExposureBreach):
        return HaltCause.PER_NAME_CAP_BREACH
    if isinstance(exc, NetExposureBreach):
        return HaltCause.NET_CAP_BREACH
    return HaltCause.PLANNING_FAILED


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
