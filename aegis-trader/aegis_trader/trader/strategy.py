"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

Slice 3: InstrumentRef→InstrumentId resolution via the venue-native provider.
A bimap is built at ``on_start``; netting stays in InstrumentRef space,
resolution to venue-specific InstrumentIds only at the execution edge (order
submission).

RiskEngine guards (Slice 8): the ``RiskGuard`` computes per-instrument
max-notional caps from NAV; the strategy logs every ``OrderDenied`` event
so operators can trace rejected orders.

Slice 6 — cadence (per-sleeve timeframe + calendar-aware):
- Each sleeve rebalances off bar-close at its own DataContract.timeframe.
- Debounced: one re-net per completed period, not per-instrument-bar churn.
- Calendar-aware: orders emitted only for instruments whose venue is open
  (had a fresh bar during the completed period).
- Drift is evaluated every period even on an unchanged target.

Slice 7 - reconciliation (integrity-halt): an account-integrity check at
startup (cache health, account ID, NAV/cash consistency) halts the book
globally on failure.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_data.roll import DEFAULT_ROLL_LEAD_DAYS, DatedContract
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
from aegis_trader.data import (
    MarketDataPort,
    NautilusMarketData,
    bar_type,
    resolve_book_timeframe,
    timeframe_to_ns,
)
from aegis_trader.domain.allocator import portfolio_skew
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import IntegrityReport, check_account_integrity
from aegis_trader.domain.rebalancer import rebalance_plan
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.roll import HeldContract, roll_positions
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.types import (
    OrderIntent,
    OrderSide,
    OrderSource,
    ResolvedContractId,
    SleeveName,
)
from aegis_trader.execution.figi_resolver import (
    FigiInstrumentResolver,
    FigiResolutionError,
)
from aegis_trader.trader.instrument_provider import (
    declared_ref_currencies,
    loaded_futures_ref_bimap,
    loaded_listed_ref_bimap,
    reconcile_quote_currency,
)
from aegis_trader.observability.port import (
    GateOutcome,
    ObservabilityPort,
    RebalanceSummary,
)
from aegis_trader.portfolio import BookStatePort, NautilusBookState

_NS_PER_DAY: int = 86_400_000_000_000
_MIN_SLEEVE_VOL_RETURNS = 20
_TRADING_DAYS_PER_YEAR = 252.0
_EWMA_COVARIANCE_ALPHA = 0.06
_MIN_BOOK_SKEW_RETURNS = 8


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    figi_resolver: FigiInstrumentResolver | None = None
    risk_guard_config: RiskGuardConfig = RiskGuardConfig()
    obs_port: ObservabilityPort | None = None
    futures_contract_chains: dict[str, tuple[DatedContract, ...]] | None = None
    futures_roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS
    fill_time_in_force: TimeInForce | None = None
    """Time-in-force for submitted orders (ADR-0001, next-close execution).

    ``None`` (backtest): a plain ``MARKET`` order fills at the execution bar's
    close — the SimulatedExchange rejects session TIFs.  ``AT_THE_CLOSE``
    (paper/live): a Market-on-Close order into the closing auction.  Set by the
    mode builders in ``trader/modes.py`` so backtest and live model the same
    fill point (the close)."""


class RebalanceStrategy(Strategy):
    """Commingled-book rebalance overlay — submits orders NEXT-CLOSE.

    Per-sleeve timeframe cadence (Slice 6):
    - Bars are buffered per instrument as they arrive.
    - When the period (day) changes, a rebalance is triggered for the
      *completed* period using all bars buffered up to that point.
    - Each sleeve's bundle computes targets from its own buffered bars
      (per-sleeve-latest as-of), netted across sleeves, and orders are
      emitted only for FIGIs whose venue was open (had a fresh bar) during
      the completed period.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._book: BookConfig = config.book
        # ── Slice 6 sleeve registry ──────────────────────────────────────
        self._sleeve_to_bundle: dict[SleeveName, ExecutionBundle] = {}
        self._sleeve_to_contract: dict[SleeveName, DataContract] = {}
        self._instr_to_figi: dict[str, InstrumentRef] = {}  # InstrumentId.value → InstrumentRef (bimap inverse)
        # ── bar buffers & cadence state ──────────────────────────────────
        self._bars_buffer: dict[InstrumentId, list[Bar]] = {}
        self._current_period: int | None = None
        self._period_fresh_figis: set[InstrumentRef] = set()
        # Rebalance-period width in ns; set from the book timeframe in on_start.
        self._period_ns: int = _NS_PER_DAY
        # Book bar timeframe (one across sleeves); set in on_start, reused to
        # subscribe a contract the book rolls into mid-run.
        self._book_timeframe: str | None = None
        # ── Slice 3: FIGI bimap ──────────────────────────────────────────
        self._figi_bimap: dict[InstrumentRef, InstrumentId] = {}
        self._figi_resolver: FigiInstrumentResolver = (
            config.figi_resolver if config.figi_resolver is not None
            else FigiInstrumentResolver()
        )
        self._futures_contract_chains: dict[str, tuple[DatedContract, ...]] = (
            config.futures_contract_chains or {}
        )
        self._futures_roll_lead_days: int = config.futures_roll_lead_days
        # ── Slice 8: RiskEngine guards ───────────────────────────────────
        self._risk_guard: RiskGuard = RiskGuard(config.risk_guard_config)
        # Slice 7: account-integrity check + global halt
        self._integrity_report: IntegrityReport | None = None
        self._is_halted: bool = False
        # Wave B: reconciled book state behind a port (no direct cache/portfolio reads).
        self._book_state: BookStatePort | None = None
        self._market_data: MarketDataPort | None = None
        # Wave B (B14): real per-period NAV history feeding on_stop attribution.
        self._nav_history: list[float] = []
        self._last_attribution: dict[SleeveName, float] = {}
        self._last_book_skew: float | None = None
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        self._last_roll_check_date: date | None = None
        # ── Slice 9: observability + attribution ─────────────────────────
        self._obs_port: ObservabilityPort | None = config.obs_port
        # Per-period inputs for the realized-weight sleeve attribution (on_stop).
        self._attribution_periods: list[AttributionPeriod] = []

    # ── public API ────────────────────────────────────────────────────────────

    def register_sleeve(
        self, name: SleeveName, bundle: ExecutionBundle,
    ) -> None:
        """Register a sleeve with its backing ExecutionBundle.

        Replaces the Slice 1 ``_bundle`` direct-set pattern — call this
        before the engine starts for each sleeve declared in the BookConfig.
        """
        self._sleeve_to_bundle[name] = bundle
        self._sleeve_to_contract[name] = bundle.contract

    # ── port accessors ──────────────────────────────────────────────────────
    # The reconciled-book and market-data ports are wired in ``on_start``; every
    # trading path runs after it.  These accessors make that lifecycle invariant
    # explicit and fail fast if a path is ever reached before the engine starts.

    def _require_book_state(self) -> BookStatePort:
        if self._book_state is None:
            raise RuntimeError("book-state port queried before on_start wired it")
        return self._book_state

    def _require_market_data(self) -> MarketDataPort:
        if self._market_data is None:
            raise RuntimeError("market-data port queried before on_start wired it")
        return self._market_data

    # ── Nautilus lifecycle ────────────────────────────────────────────────────

    def on_start(self) -> None:
        if not self._sleeve_to_bundle:
            self.log.warning("No sleeves registered; strategy will idle.")
            return

        # Wave B (B13): reject at load if any book cap exceeds its sleeve
        # bundle's research-validated cap.  A misconfigured book never trades.
        try:
            check_cap_provenance(self._book, self._sleeve_to_bundle)
        except CapProvenanceError as exc:
            self.log.error(f"Cap provenance FAILED: {exc}. HALTING the book.")
            self._is_halted = True
            if self._obs_port is not None:
                self._obs_port.alert_halt(str(exc))
            return

        # ── Slice 7: account-integrity check at startup ──────────────────
        base_ccy = Currency.from_str(self._book.base_currency)
        self._book_state = NautilusBookState(
            portfolio=self.portfolio,
            cache=self.cache,
            base_currency=base_ccy,
            instr_to_figi=self._instr_to_figi,
        )
        self._market_data = NautilusMarketData(cache=self.cache)

        try:
            nav = self._book_state.nav()
            cash = self._book_state.cash()
        except Exception as exc:
            self.log.error(
                f"Failed to query book state for integrity check: {exc}. "
                f"Marking NAV/cash as zero."
            )
            nav = 0.0
            cash = 0.0

        cache_healthy = self._book_state.is_cache_healthy()
        self._integrity_report = check_account_integrity(
            nav=nav,
            cash=cash,
            cache_healthy=cache_healthy,
        )
        if not self._integrity_report.healthy:
            self.log.error(
                f"Integrity check FAILED: {self._integrity_report.reason}. "
                f"HALTING the book."
            )
            self._is_halted = True
            if self._obs_port is not None:
                self._obs_port.alert_halt(self._integrity_report.reason or "Unknown integrity failure")
            return

        self.log.info(f"Integrity check passed: NAV={nav:.2f}, cash={cash:.2f}")

        # Collect all unique FIGIs across all sleeves.
        all_figis: set[InstrumentRef] = set()
        for bundle in self._sleeve_to_bundle.values():
            all_figis.update(bundle.contract.refs)

        # Resolve refs to venue-native InstrumentIds via the Security Master,
        # as-of the boot date.  The bimap is the SINGLE source of truth for
        # instrument identity - every subscription, bar buffer, sizing read,
        # order, and risk cap keys off it.  A ListedRef resolves date-invariantly;
        # a FuturesRef resolves to its live contract for the boot date and is
        # re-resolved at the roll cadence (see _refresh_resolution).  (A stub
        # bimap may be injected by e2e tests.)
        if not self._figi_bimap:
            self._figi_bimap = self._resolve_bimap(all_figis, self._as_of())

        # Subscribe to bars on the RESOLVED InstrumentId and build the inverse
        # (InstrumentId -> FIGI) map used for position lookups.
        # The book runs on one timeframe (all sleeves agree); resolve it once for
        # the bar subscription and the rebalance-period width.
        book_timeframe = resolve_book_timeframe(
            contract.timeframe for contract in self._sleeve_to_contract.values()
        )
        self._book_timeframe = book_timeframe
        self._period_ns = timeframe_to_ns(book_timeframe)

        for figi in sorted(all_figis):  # stable subscription order (aegis-rd-10d)
            instr_id = self._figi_to_instr_id(figi)
            self._instr_to_figi[instr_id.value] = figi
            self.subscribe_bars(bar_type(instr_id.value, book_timeframe))

        # Subscribe to FX reference-pair quotes so the cache mark xrates stay
        # current from live data — both the sizer (MarketDataPort.fx_rate) and
        # base valuation (NautilusBookState) read get_mark_xrate.  The overlay
        # never trades these pairs; it only mirrors their quotes into marks
        # (on_quote_tick).  Pairs are discovered from the reconciled cache (loaded
        # by the venue's instrument provider in live, fed as data in backtest), so
        # no broker-specific ids are constructed here (ADR-0003).
        for instrument in self.cache.instruments():
            if isinstance(instrument, CurrencyPair):
                self.subscribe_quote_ticks(instrument.id)

        names = [s.value for s in self._sleeve_to_bundle]
        self.log.info(
            f"RebalanceStrategy starting; sleeves={names}, "
            f"bimap={ {f: i.value for f, i in self._figi_bimap.items()} }"
        )

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Mirror an FX reference pair's quote into the cache mark xrate.

        ``set_mark_xrate`` also sets the inverse, so this is orientation- and
        venue-agnostic: ``get_mark_xrate(base, ccy)`` then resolves whichever way
        the pair is quoted, on whatever venue it trades.  Non-FX quotes (no
        ``CurrencyPair`` behind them) are ignored.
        """
        instrument = self.cache.instrument(tick.instrument_id)
        if not isinstance(instrument, CurrencyPair):
            return
        mid = (tick.bid_price.as_double() + tick.ask_price.as_double()) / 2.0
        if mid <= 0.0:
            return
        self.cache.set_mark_xrate(instrument.base_currency, instrument.quote_currency, mid)

    def on_bar(self, bar: Bar) -> None:
        """Buffer bar and trigger a period-level rebalance when the period advances.

        Debounce (Slice 6): only one re-net per completed period, not
        per-instrument.  When the first bar of a new period arrives the
        strategy rebalances using all bars from the *completed* period and
        submits orders that will fill at the *new* period's close — one-bar
        execution lag.
        """
        if not self._sleeve_to_bundle or self._is_halted:
            return

        instr_id = bar.bar_type.instrument_id
        as_of = self._as_of()
        if self._last_roll_check_date != as_of:
            # Re-resolve FuturesRefs as-of today FIRST, so the bimap (and hence
            # every drift order this tick) points at the current contract; then
            # migrate any held position off the contract it just rolled out of.
            self._refresh_resolution(as_of)
            self._submit_roll_orders(as_of)
            self._last_roll_check_date = as_of
        period = self._extract_period(bar)

        # ── period-advance → rebalance the completed period ──────────────
        if self._current_period is not None and period != self._current_period:
            self._rebalance_for_period()
            self._period_fresh_figis = set()

        # ── buffer the bar AFTER the rebalance (so rebalance only sees
        #    completed-period bars — no same-bar look-ahead) ──────────────
        buf = self._bars_buffer.setdefault(instr_id, [])
        buf.append(bar)

        # Trim to lookback_needed bars (use max lookback across sleeves)
        max_lookback = max(
            c.lookback_bars for c in self._sleeve_to_contract.values()
        )
        needed = max_lookback + 1
        if len(buf) > needed:
            buf[:] = buf[-needed:]

        if self._current_period is None:
            self._current_period = period
        else:
            self._current_period = period

        figi = self._instr_to_figi.get(instr_id.value)
        if figi:
            self._period_fresh_figis.add(figi)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _extract_period(self, bar: Bar) -> int:
        """The rebalance period index for *bar*: its event timestamp floored to
        the book's bar width (set from the contract timeframe in on_start)."""
        return bar.ts_event // self._period_ns

    def _rebalance_for_period(self) -> None:
        """Compute per-sleeve targets from buffered bars, net, and submit.

        Each sleeve computes on its own most-recent completed bars
        (per-sleeve-latest as-of).  Orders are filtered to only FIGIs whose
        venue was open during the completed period (calendar-aware).

        Slice 5: collects per-FIGI instrument metadata, close prices, and
        FX rates from Nautilus and passes them through to the rebalancer for
        sizing (EUR notional → native share quantity with GBp pence + increment
        rounding).
        """
        if self._is_halted:
            return

        pending: dict[SleeveName, pd.DataFrame] = {}

        for sleeve in self._book.sleeves:
            bundle = self._sleeve_to_bundle.get(sleeve.name)
            if bundle is None:
                continue
            contract = bundle.contract
            lookback = contract.lookback_bars
            needed = lookback + 1

            # Collect each FIGI's completed-period bar buffer (enough lookback).
            sleeve_bufs: dict[str, list[Bar]] = {}
            sleeve_ok = True
            for figi in contract.refs:
                instr_id = self._figi_to_instr_id(figi)
                buf = self._bars_buffer.get(instr_id, [])
                if len(buf) < needed:
                    sleeve_ok = False
                    break
                sleeve_bufs[figi] = buf

            if not sleeve_ok or not sleeve_bufs:
                continue

            # Assemble one DataFrame per array the contract declares (a column per
            # FIGI), sourced from the buffered bars — the overlay feeds
            # compute_weights exactly the arrays the bundle asked for.
            arrays = {
                name: _combine_array_series(sleeve_bufs, name)
                for name in contract.required_arrays
            }
            bundle_data = MarketDataBundle(arrays)
            fx_series = self._fx_series_for(contract, next(iter(arrays.values())).index)
            if fx_series is None:
                self.log.warning(
                    f"sleeve {sleeve.name.value}: required FX unavailable; "
                    f"skipping (fail closed, no fabricated rate)"
                )
                continue
            target = bundle.compute_weights(bundle_data, fx_series=fx_series)
            pending[sleeve.name] = target

        if not pending:
            return

        # Net all sleeve targets and submit
        nav = self._require_book_state().nav()

        instrument_metas, fx_rates, prices = self._collect_sizing_params()
        realized_weights = self._require_book_state().realized_weights()

        # Two-step pipeline: the pure rebalancer decides what to trade (signed
        # weight deltas) against the REALIZED book (so bands, the realized-book
        # gate, and the fidelity trip engage); the sizer converts each delta into
        # a native share count.
        realized_covariance = self._realized_sleeve_covariance()
        plan = rebalance_plan(
            pending,
            self._book,
            realized_weights=realized_weights,
            realized_covariance=realized_covariance,
            previous_sleeve_weights=self._last_sleeve_weights,
            realized_drawdown=current_drawdown(self._nav_history, nav),
        )
        self._last_sleeve_weights = dict(plan.applied_sleeve_weights)
        orders = size_deltas(
            plan.deltas,
            nav,
            instrument_metas=instrument_metas,
            fx_rates=fx_rates,
            prices=prices,
        )

        # ── Slice 9: compute total notional for the summary ──────────────
        total_notional = sum(
            abs(o.quantity) for o in orders
            if o.ref in self._period_fresh_figis
        )

        # ── Slice 9: build and log the rebalance summary ─────────────────
        # After netting there is at most one OrderIntent per FIGI, so
        # num_targets (distinct FIGIs with non-zero net) equals num_orders.
        summary = RebalanceSummary(
            nav=nav,
            num_sleeves=len(pending),
            num_targets=len(orders),
            num_orders=len(orders),
            gate_outcome=GateOutcome.PASS,
            total_notional=total_notional,
        )
        self._log_rebalance_summary(summary)


        # ── Slice 9: store per-sleeve targets & closes for attribution ───
        # Record this period's realized weights, per-sleeve target rows, and
        # closes so on_stop can decompose the realized-weight book P&L by sleeve.
        # Each pending target is non-empty: rebalance() above took iloc[-1].
        self._nav_history.append(nav)
        self._attribution_periods.append(
            AttributionPeriod(
                nav=nav,
                realized_weights=dict(realized_weights),
                sleeve_targets={
                    name: {
                        _column_ref(figi): float(weight)
                        for figi, weight in target_df.iloc[-1].to_dict().items()
                    }
                    for name, target_df in pending.items()
                },
                closes=dict(prices),
            )
        )

        # Calendar-aware: only emit orders for FIGIs with a fresh bar
        for oi in orders:
            if oi.ref not in self._period_fresh_figis:
                self.log.info(
                    f"Skipping {oi.side.value} {oi.quantity:.0f} "
                    f"{oi.ref.value}: venue closed this period"
                )
                continue
            self._submit_order_intent(oi)

    def _refresh_resolution(self, as_of: date) -> None:
        """Re-resolve each FuturesRef as-of *as_of*; when its live contract has
        changed, point the bimap at the new contract, map the new contract back
        in the inverse, and subscribe its bars.

        ListedRefs are date-invariant and skipped.  The inverse keeps the old
        contract mapped so a not-yet-closed position still folds back to its ref
        for the roll check and the realized book.
        """
        if self._book_timeframe is None:
            return
        for ref in list(self._figi_bimap):
            if not isinstance(ref, FuturesRef):
                continue
            new_id = self._resolve_instrument_id(ref, as_of)
            if new_id == self._figi_bimap[ref]:
                continue
            self._figi_bimap[ref] = new_id
            self._instr_to_figi[new_id.value] = ref
            self.subscribe_bars(bar_type(new_id.value, self._book_timeframe))

    def _submit_roll_orders(self, as_of: date) -> None:
        held = self._held_contracts_for_roll()
        if not held:
            return
        orders = roll_positions(held, as_of=as_of, resolve=self._resolve_contract_id_for_roll)
        for order in orders:
            self._submit_order_intent(order)

    def _held_contracts_for_roll(self) -> tuple[HeldContract, ...]:
        held: list[HeldContract] = []
        for position in self.cache.positions_open():
            ref = self._instr_to_figi.get(position.instrument_id.value)
            if ref is None:
                continue
            quantity = float(position.quantity.as_double())
            if position.is_short:
                quantity = -quantity
            held.append(
                HeldContract(
                    ref=ref,
                    contract_id=ResolvedContractId(position.instrument_id.value),
                    quantity=quantity,
                )
            )
        return tuple(held)

    def _resolve_contract_id_for_roll(self, ref: InstrumentRef, as_of: date) -> ResolvedContractId:
        instrument_id = self._resolve_instrument_id(ref, as_of)
        # Keep the inverse map current as the ref rolls: a position folded onto
        # the rolled-into contract must resolve back to its InstrumentRef, so the
        # realized book (and the next base-tick roll check) reason in continuous
        # space rather than re-buying the stale front contract.
        self._instr_to_figi[instrument_id.value] = ref
        return ResolvedContractId(instrument_id.value)

    def _resolve_instrument_id(self, ref: InstrumentRef, as_of: date) -> InstrumentId:
        """Resolve a ref to its venue-native InstrumentId as-of *as_of* via the
        Security Master.  A ListedRef ignores ``as_of`` (date-invariant); a
        FuturesRef selects its live dated contract for that date."""
        if isinstance(ref, FuturesRef) and self._futures_contract_chains:
            return self._loaded_futures_bimap((ref,), as_of)[ref]
        instrument_id = self._figi_resolver.resolve(ref, as_of=as_of)
        if not isinstance(instrument_id, InstrumentId):
            raise FigiResolutionError(f"resolution for {ref!r} did not return an InstrumentId")
        return instrument_id

    def _as_of(self) -> date:
        """The current trading date from the clock (TestClock in backtest,
        LiveClock in paper/live) — one source for backtest=live parity."""
        return self.clock.utc_now().date()

    def _log_rebalance_summary(self, summary: RebalanceSummary) -> None:
        """Emit a structured rebalance log through the observability port.

        Falls back to ``self.log.info`` when no port is configured.
        """
        if self._obs_port is not None:
            self._obs_port.log_rebalance_decision(summary)
        else:
            self.log.info(
                f"Rebalance: NAV={summary.nav:.2f} "
                f"sleeves={summary.num_sleeves} "
                f"targets={summary.num_targets} "
                f"orders={summary.num_orders} "
                f"gate={summary.gate_outcome.value} "
                f"notional={summary.total_notional:.2f}"
            )

    def _realized_sleeve_covariance(self) -> dict[SleeveName, dict[SleeveName, float]] | None:
        """Estimate annualized sleeve covariance from recorded period data.

        The estimate uses only bars already consumed by the strategy: each
        sleeve's raw target weights held from period t to t+1 are multiplied by
        the observed instrument returns over that same interval.  Until every
        positive-risk sleeve has enough complete, non-degenerate returns, return
        ``None`` so the rebalancer sizes from the configured risk budget (the
        base allocation) rather than solving on an undefined covariance matrix.
        """
        if len(self._attribution_periods) < _MIN_SLEEVE_VOL_RETURNS + 1:
            return None

        names = self._positive_risk_sleeve_names()
        periods = self._attribution_periods[-(_MIN_SLEEVE_VOL_RETURNS + 1):]
        rows = _complete_sleeve_return_rows(periods, names)
        if len(rows) < _MIN_SLEEVE_VOL_RETURNS:
            return None
        return _annualized_covariance_by_sleeve(names, rows)

    def _positive_risk_sleeve_names(self) -> tuple[SleeveName, ...]:
        """Return the sleeve universe shared by covariance and skew estimates."""
        risk_shares = self._book.allocator_risk_shares()
        return tuple(
            sleeve.name for sleeve in self._book.sleeves if risk_shares[sleeve.name] > 0
        )

    def _record_book_skew(self) -> None:
        """Record the book's realized skew as evidence (aegis-rd-ytr.2).

        Net-convexity is delivered by construction (ADR-0004 amendment), not
        enforced; this surfaces *whether* it holds for the applied allocation so
        a net-concave book is seen rather than silently re-weighted toward
        convexity.  Stays ``None`` until enough complete return rows exist to
        define a skew.
        """
        names = self._positive_risk_sleeve_names()
        rows = _complete_sleeve_return_rows(self._attribution_periods, names)
        if len(rows) < _MIN_BOOK_SKEW_RETURNS:
            return
        realized_returns = {
            name: tuple(row[index] for row in rows)
            for index, name in enumerate(names)
        }
        weights = {name: self._last_sleeve_weights.get(name, 0.0) for name in names}
        self._last_book_skew = portfolio_skew(weights, realized_returns)
        convexity = "convex" if self._last_book_skew >= 0.0 else "concave"
        self.log.info(
            f"Realized book skew: {self._last_book_skew:+.3f} (net-{convexity})"
        )

    def on_stop(self) -> None:
        """Record end-of-run evidence: realized book skew and per-sleeve P&L.

        Decomposes the realized-weight book P&L across sleeves by their
        budget-scaled target share (compute_sleeve_attribution); needs at
        least two recorded rebalance periods.  The realized-book-skew recording
        has its own (longer) history requirement and runs first.
        """
        self._record_book_skew()

        if len(self._attribution_periods) < 2:
            return

        risk_shares = self._book.allocator_risk_shares()
        attribution = compute_sleeve_attribution(
            self._attribution_periods, budgets=risk_shares
        )
        self._last_attribution = attribution

        if attribution:
            total_book_pnl = sum(attribution.values())
            parts = ", ".join(
                f"{s.value}={pnl:.2f}" for s, pnl in attribution.items()
            )
            self.log.info(
                f"Per-sleeve P&L attribution: {parts} "
                f"(book total={total_book_pnl:.2f})"
            )

    def _figi_to_instr_id(self, figi: InstrumentRef) -> InstrumentId:
        """Resolve a FIGI to a venue-specific InstrumentId.

        Fails closed (raises) when the FIGI was not resolved: the book never
        acts on an unidentified instrument, and never reconstructs identity by
        parsing strings (ADR-0002).
        """
        instr_id = self._figi_bimap.get(figi)
        if instr_id is None:
            raise FigiResolutionError(
                f"InstrumentRef {figi!r} is not in the resolved bimap; refusing to act "
                f"on an unidentified instrument"
            )
        return instr_id

    def _resolve_bimap(
        self, refs: set[InstrumentRef], as_of: date
    ) -> dict[InstrumentRef, InstrumentId]:
        """Resolve *refs* to a bimap via the Security Master, as-of *as_of*.

        ListedRefs resolve from the IB InstrumentProvider-loaded cache;
        FuturesRefs resolve to their live dated contract for *as_of*,
        individually (each carries its own roll calendar).
        """
        listed: set[ListedRef] = {r for r in refs if isinstance(r, ListedRef)}
        futures = sorted(r for r in refs if isinstance(r, FuturesRef))
        bimap: dict[InstrumentRef, InstrumentId] = {}
        if listed:
            bimap.update(loaded_listed_ref_bimap(listed, self.cache.instruments()))
        if futures and self._futures_contract_chains:
            bimap.update(self._loaded_futures_bimap(futures, as_of))
        else:
            for ref in futures:
                bimap[ref] = self._resolve_instrument_id(ref, as_of)
        return bimap

    def _loaded_futures_bimap(
        self, refs: Iterable[FuturesRef], as_of: date
    ) -> dict[FuturesRef, InstrumentId]:
        return loaded_futures_ref_bimap(
            refs,
            self.cache.instruments(),
            as_of=as_of,
            contract_chains=self._futures_contract_chains,
            roll_lead_days=self._futures_roll_lead_days,
        )

    def _collect_sizing_params(
        self,
    ) -> tuple[dict[InstrumentRef, InstrumentSizing], dict[str, float], dict[InstrumentRef, float]]:
        """Gather per-FIGI instrument metadata, FX rates, and latest close
        prices from Nautilus for sizing.

        Returns three dicts keyed by :class:`InstrumentRef` (instrument_metas/prices) or
        currency (fx_rates).  An instrument that cannot be resolved from the
        cache is silently omitted (the rebalancer will fall back to raw
        notional for it).
        """
        instrument_metas: dict[InstrumentRef, InstrumentSizing] = {}
        prices: dict[InstrumentRef, float] = {}
        currencies: set[str] = set()

        refs: set[InstrumentRef] = set()
        for bundle in self._sleeve_to_bundle.values():
            refs.update(bundle.contract.refs)
        declared_currencies = declared_ref_currencies(self._sleeve_to_bundle.values())

        for ref in refs:
            instr_id = self._figi_to_instr_id(ref)
            sizing = self._require_market_data().instrument_sizing(instr_id)
            if sizing is None:
                continue

            quote_currency = reconcile_quote_currency(ref, sizing.currency, declared_currencies)
            instrument_metas[ref] = InstrumentSizing(
                currency=quote_currency,
                size_increment=sizing.size_increment,
            )

            buf = self._bars_buffer.get(instr_id)
            if buf:
                prices[ref] = float(buf[-1].close.as_double())

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
        """Build the base→ccy FX series a bundle needs for its
        ``required_fx_currencies``, sourced live from the MarketDataPort.

        Returns ``{}`` when no FX is needed, or ``None`` when a required rate is
        unavailable — the caller then skips the sleeve (fail closed; the bundle
        is never run on a fabricated or absent rate).
        """
        needed = contract.required_fx_currencies
        if not needed:
            return {}
        base = self._book.base_currency
        series: dict[str, pd.Series] = {}
        for ccy in needed:
            rate = self._require_market_data().fx_rate(base, ccy)
            if rate is None:
                return None
            series[ccy] = pd.Series(rate, index=index)
        return series

    def _get_fx_rate(self, target_currency: str) -> float | None:
        """FX rate as the instrument's MAJOR quote currency per 1 base — e.g.
        GBP per EUR for a GBP or GBp instrument (the GBp pence factor is applied
        inside ``sizing.size_order``).

        Sourced live from the MarketDataPort.  Returns 1.0 when the major currency
        is the base, and None when no rate is available — the instrument is then
        left unsized (fail closed; no fabricated FX).
        """
        base = self._book.base_currency
        major = major_currency(target_currency)
        if major == base:
            return 1.0
        return self._require_market_data().fx_rate(base, major)

    # -- RiskEngine callbacks ---------------------------------------------------

    def on_order_denied(self, event: OrderDenied) -> None:
        """Log every order denial from the RiskEngine.

        A denial means the RiskEngine rejected the order before submission —
        protects against oversized orders and other pre-trade violations.
        """
        self.log.warning(
            f"OrderDenied: instrument={event.instrument_id!r} "
            f"client_order_id={event.client_order_id!r} "
            f"reason={event.reason!r}"
        )

    def risk_engine_config_dict(self, nav: float) -> dict[str, Any]:
        """Return a dict suitable for ``RiskEngineConfig`` kwargs.

        Computes per-instrument max notionals from the current NAV, keyed by each
        FIGI's *resolved* InstrumentId (so every instrument carries its own
        venue).  FIGIs absent from the bimap are skipped — the caps are only as
        complete as the resolution.
        """
        instrument_ids: list[str] = [
            self._figi_bimap[figi].value
            for contract in self._sleeve_to_contract.values()
            for figi in contract.refs
            if figi in self._figi_bimap
        ]
        return self._risk_guard.risk_engine_config_dict(
            nav=nav,
            instrument_ids=instrument_ids,
        )

    # -- order submission -------------------------------------------------------

    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit.

        The quantity is already a native share count (sized by the rebalancer),
        so it is passed directly to ``make_qty``.
        """
        instr_id = (
            InstrumentId.from_str(oi.resolved_contract_id.value)
            if oi.resolved_contract_id is not None
            else self._figi_to_instr_id(oi.ref)
        )
        quantity = self._require_market_data().make_quantity(instr_id, oi.quantity)
        if quantity is None:
            self.log.error(
                f"Instrument not found for InstrumentRef {oi.ref.value}; skipping order"
            )
            return

        nt_side = NtOrderSide.BUY if oi.side == OrderSide.BUY else NtOrderSide.SELL
        kwargs: dict[str, Any] = {
            "instrument_id": instr_id,
            "order_side": nt_side,
            "quantity": quantity,
        }
        # NEXT-CLOSE (ADR-0001): backtest leaves the factory default (plain MARKET
        # fills at the bar close); paper/live carry AT_THE_CLOSE (Market-on-Close).
        if self.config.fill_time_in_force is not None:
            kwargs["time_in_force"] = self.config.fill_time_in_force
        if oi.source == OrderSource.ROLL:
            self.log.info(
                f"Roll order: {oi.side.value} {oi.quantity:.0f} {instr_id.value} for {oi.ref.value}"
            )
        order = self.order_factory.market(**kwargs)
        self.submit_order(order)


def _column_ref(column: object) -> InstrumentRef:
    if isinstance(column, ListedRef | FuturesRef):
        return column
    return ListedRef(str(column))


def current_drawdown(nav_history: list[float], current_nav: float) -> float:
    """Return current drawdown from the running NAV peak as a fraction."""
    if not np.isfinite(current_nav):
        raise ValueError("current NAV must be finite")
    peak = max([float(current_nav), *(float(nav) for nav in nav_history)])
    if peak <= 0.0:
        return 0.0
    drawdown = 1.0 - float(current_nav) / peak
    return min(max(drawdown, 0.0), 1.0)


_BAR_ARRAY_ACCESSORS: dict[str, Callable[[Bar], float]] = {
    "Open": lambda b: float(b.open.as_double()),
    "High": lambda b: float(b.high.as_double()),
    "Low": lambda b: float(b.low.as_double()),
    "Close": lambda b: float(b.close.as_double()),
    "Volume": lambda b: float(b.volume.as_double()),
}


def _bars_to_array_series(bars: list[Bar], figi: str, array_name: str) -> pd.DataFrame:
    """Convert buffered bars into a single-column DataFrame of the named OHLCV
    array (Open/High/Low/Close/Volume) keyed by *figi*."""
    accessor = _BAR_ARRAY_ACCESSORS[array_name]
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [accessor(b) for b in bars]
    return pd.DataFrame({figi: values}, index=index)


def _combine_array_series(
    bufs_by_figi: dict[str, list[Bar]], array_name: str
) -> pd.DataFrame:
    """One DataFrame for *array_name* with a column per FIGI, from each FIGI's bars."""
    series = {
        figi: _bars_to_array_series(buf, figi, array_name)
        for figi, buf in bufs_by_figi.items()
    }
    if len(series) == 1:
        return next(iter(series.values()))
    return pd.concat(series.values(), axis=1)


def _complete_sleeve_return_rows(
    periods: list[AttributionPeriod],
    names: tuple[SleeveName, ...],
) -> list[list[float]]:
    """Return period return rows with one valid return per active sleeve."""
    rows: list[list[float]] = []
    for prev, curr in zip(periods, periods[1:], strict=False):
        row = _complete_period_return_row(prev, curr, names)
        if row is not None:
            rows.append(row)
    return rows


def _complete_period_return_row(
    prev: AttributionPeriod,
    curr: AttributionPeriod,
    names: tuple[SleeveName, ...],
) -> list[float] | None:
    row: list[float] = []
    for name in names:
        sleeve_return = _sleeve_period_return(prev, curr, name)
        if sleeve_return is None:
            return None
        row.append(sleeve_return)
    return row


def _sleeve_period_return(
    prev: AttributionPeriod,
    curr: AttributionPeriod,
    name: SleeveName,
) -> float | None:
    sleeve_return = 0.0
    has_input = False
    for figi, weight in prev.sleeve_targets.get(name, {}).items():
        prev_px = prev.closes.get(figi)
        curr_px = curr.closes.get(figi)
        if prev_px is None or curr_px is None or prev_px <= 0:
            continue
        sleeve_return += float(weight) * (curr_px / prev_px - 1.0)
        has_input = True
    return sleeve_return if has_input else None


def _annualized_covariance_by_sleeve(
    names: tuple[SleeveName, ...],
    rows: list[list[float]],
) -> dict[SleeveName, dict[SleeveName, float]] | None:
    covariance = _ewma_covariance(rows, alpha=_EWMA_COVARIANCE_ALPHA)
    covariance *= _TRADING_DAYS_PER_YEAR
    if not np.all(np.isfinite(covariance)):
        return None
    if np.any(np.diag(covariance) <= 0.0):
        return None
    return _covariance_dict(names, covariance)


def _covariance_dict(
    names: tuple[SleeveName, ...],
    covariance: np.ndarray,
) -> dict[SleeveName, dict[SleeveName, float]]:
    return {
        left: {right: float(covariance[i, j]) for j, right in enumerate(names)}
        for i, left in enumerate(names)
    }


def _ewma_covariance(rows: list[list[float]], *, alpha: float) -> np.ndarray:
    """Return an EWMA covariance matrix for complete return rows."""
    values = np.array(rows, dtype=float)
    mean = values[0].copy()
    covariance = np.zeros((values.shape[1], values.shape[1]), dtype=float)
    for row in values[1:]:
        diff = row - mean
        covariance = (1.0 - alpha) * covariance + alpha * np.outer(diff, diff)
        mean = (1.0 - alpha) * mean + alpha * row
    return (covariance + covariance.T) / 2.0
