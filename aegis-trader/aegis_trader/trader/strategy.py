"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

Slice 3: InstrumentRef→InstrumentId resolution via the venue-native provider.
The pipeline builds identity at ``on_start``; netting stays in InstrumentRef
space, resolution to venue-specific InstrumentIds only at the execution edge
(order submission).

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

from collections.abc import Callable
from datetime import date
from typing import Any

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
)

from aegis_trader.bundles.provenance import CapProvenanceError, check_cap_provenance
from aegis_trader.data import (
    MarketDataPort,
    NautilusMarketData,
    bar_type,
    resolve_book_timeframe,
    timeframe_to_ns,
)
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import IntegrityReport, check_account_integrity
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.roll import HeldContract, roll_positions
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import (
    OrderIntent,
    OrderSide,
    OrderSource,
    ResolvedContractId,
    SleeveName,
)
from aegis_trader.trader.instrument_provider import (
    InstrumentResolutionError,
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
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    RebalancePipeline,
)
from aegis_trader.portfolio import BookStatePort, NautilusBookState

_NS_PER_DAY: int = 86_400_000_000_000


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
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
    - When the period (day) changes, a rebalance is triggered for the
      *completed* period using the Cache-backed rolling bar window.
    - Each sleeve's bundle computes targets from its own Cache-backed bars,
      netted across sleeves, and orders are emitted only for FIGIs whose
      venue was open (had a Cache bar) during the completed period.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._book: BookConfig = config.book
        # ── Slice 6 sleeve registry ──────────────────────────────────────
        self._sleeve_to_bundle: dict[SleeveName, ExecutionBundle] = {}
        self._sleeve_to_contract: dict[SleeveName, DataContract] = {}
        # ── bar-driven cadence state ─────────────────────────────────────
        self._current_period: int | None = None
        # Rebalance-period width in ns; set from the book timeframe in on_start.
        self._period_ns: int = _NS_PER_DAY
        # Book bar timeframe (one across sleeves); set in on_start, reused to
        # subscribe a contract the book rolls into mid-run.
        self._book_timeframe: str | None = None
        # ── Slice 3: InstrumentRef → InstrumentId resolution ─────────────
        self._instrument_resolver: Callable[[InstrumentRef, date], InstrumentId] | None = None
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
        # Pure cross-period analytics ledger is injected into the per-period pipeline.
        self._sleeve_ledger: SleeveLedger = SleeveLedger()
        self._pipeline: RebalancePipeline | None = None
        self._last_attribution: dict[SleeveName, float] = {}
        self._last_book_skew: float | None = None
        self._last_sleeve_weights: dict[SleeveName, float] = {}
        self._last_roll_check_date: date | None = None
        # ── Slice 9: observability + attribution ─────────────────────────
        self._obs_port: ObservabilityPort | None = config.obs_port

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

    def set_instrument_resolver(
        self, resolver: Callable[[InstrumentRef, date], InstrumentId]
    ) -> None:
        """Inject the single resolver the pipeline uses to own identity."""
        self._instrument_resolver = resolver

    @property
    def sleeve_ledger(self) -> SleeveLedger:
        """Cross-period analytics ledger owned by the rebalance pipeline."""
        if self._pipeline is not None:
            return self._pipeline.sleeve_ledger
        return self._sleeve_ledger

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

    def _require_pipeline(self) -> RebalancePipeline:
        if self._pipeline is None:
            raise RuntimeError("rebalance pipeline queried before on_start wired it")
        return self._pipeline

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
            instrument_ref_for_id=self._ref_for_instrument_value,
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
                reason = self._integrity_report.reason or "Unknown integrity failure"
                self._obs_port.alert_halt(reason)
            return

        self.log.info(f"Integrity check passed: NAV={nav:.2f}, cash={cash:.2f}")

        # The book runs on one timeframe (all sleeves agree); resolve it once for
        # the bar subscription and the rebalance-period width.
        book_timeframe = resolve_book_timeframe(
            contract.timeframe for contract in self._sleeve_to_contract.values()
        )
        self._book_timeframe = book_timeframe
        self._period_ns = timeframe_to_ns(book_timeframe)

        resolver = self._instrument_resolver or self._provider_instrument_resolver()
        declared_currencies = declared_ref_currencies(self._sleeve_to_bundle.values())
        self._pipeline = RebalancePipeline(
            book_state=self._require_book_state(),
            market_data=self._require_market_data(),
            book=self._book,
            sleeve_to_bundle=self._sleeve_to_bundle,
            ledger=self._sleeve_ledger,
            resolve_instrument=resolver,
            reconcile_ref_currency=lambda ref, currency: reconcile_quote_currency(
                ref, currency, declared_currencies
            ),
        )
        self._pipeline.initialize_identity(self._as_of())

        identity = self._pipeline.resolved_identity_snapshot()
        for ref, instr_id in identity.items():
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
            f"identity={ {f: i.value for f, i in identity.items()} }"
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
        """Trigger a period-level rebalance when the period advances.

        Debounce (Slice 6): only one re-net per completed period, not
        per-instrument.  When the first bar of a new period arrives the
        strategy rebalances from the Cache-backed completed-period window and
        submits orders that will fill at the *new* period's close — one-bar
        execution lag.
        """
        if not self._sleeve_to_bundle or self._is_halted:
            return

        as_of = self._as_of()
        if self._last_roll_check_date != as_of:
            # Re-resolve FuturesRefs as-of today FIRST, so pipeline identity
            # (and hence every drift order this tick) points at the current contract; then
            # migrate any held position off the contract it just rolled out of.
            self._refresh_resolution(as_of)
            self._submit_roll_orders(as_of)
            self._last_roll_check_date = as_of
        period = self._extract_period(bar)

        # ── period-advance → rebalance the completed period ──────────────
        if self._current_period is not None and period != self._current_period:
            self._rebalance_for_period()

        self._current_period = period

    # ── internal helpers ──────────────────────────────────────────────────────

    def _extract_period(self, bar: Bar) -> int:
        """The rebalance period index for *bar*: its event timestamp floored to
        the book's bar width (set from the contract timeframe in on_start)."""
        return bar.ts_event // self._period_ns

    def _rebalance_for_period(self) -> None:
        """Delegate completed-period orchestration to RebalancePipeline."""
        if self._is_halted:
            return

        pipeline = self._require_pipeline()
        if self._current_period is None:
            return
        result = pipeline.rebalance_period(
            CompletedRebalancePeriod(
                period=self._current_period,
                period_ns=self._period_ns,
            )
        )
        self._last_sleeve_weights = pipeline.last_sleeve_weights
        if result.summary.num_sleeves == 0:
            return

        self._log_rebalance_summary(result.summary)
        if result.summary.gate_outcome == GateOutcome.ERROR:
            self._is_halted = True
            reason = result.halt_reason or "rebalance gate failed"
            self.log.error(f"Rebalance gate FAILED: {reason}. HALTING the book.")
            if self._obs_port is not None:
                self._obs_port.alert_halt(reason)
            return

        for oi in result.orders:
            self._submit_order_intent(oi)

    def _refresh_resolution(self, as_of: date) -> None:
        """Re-resolve FuturesRefs and subscribe contracts that rolled in.

        The pipeline keeps old inverse entries so a not-yet-closed position still
        folds back to its continuous ref for the roll check and realized book.
        """
        if self._book_timeframe is None:
            return
        changes = self._require_pipeline().refresh_resolution(as_of)
        for change in changes:
            self.subscribe_bars(bar_type(change.current.value, self._book_timeframe))

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
            ref = self._require_pipeline().ref_for_instrument_value(position.instrument_id.value)
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
        return self._require_pipeline().resolve_contract_id_for_roll(ref, as_of)

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
        weights = {name: self._last_sleeve_weights.get(name, 0.0) for name in names}
        self._last_book_skew = self.sleeve_ledger.realized_book_skew(weights, names)
        if self._last_book_skew is None:
            return
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

        if self.sleeve_ledger.observation_count < 2:
            return

        risk_shares = self._book.allocator_risk_shares()
        attribution = self.sleeve_ledger.attribution(risk_shares)
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

    def _instrument_id_for_ref(self, ref: InstrumentRef) -> InstrumentId:
        """Return the pipeline-owned current InstrumentId for an InstrumentRef."""
        return self._require_pipeline().instrument_id_for_ref(ref)

    def _ref_for_instrument_value(self, instrument_id_value: str) -> InstrumentRef | None:
        if self._pipeline is None:
            return None
        return self._pipeline.ref_for_instrument_value(instrument_id_value)

    def _provider_instrument_resolver(self) -> Callable[[InstrumentRef, date], InstrumentId]:
        """Live resolver backed by provider-loaded cache instruments."""

        def resolve(ref: InstrumentRef, as_of: date) -> InstrumentId:
            if isinstance(ref, ListedRef):
                return loaded_listed_ref_bimap((ref,), self.cache.instruments())[ref]
            if isinstance(ref, FuturesRef):
                if not self._futures_contract_chains:
                    raise InstrumentResolutionError(
                        f"FuturesRef root {ref.root!r} has no provider-loaded contract chain"
                    )
                return loaded_futures_ref_bimap(
                    (ref,),
                    self.cache.instruments(),
                    as_of=as_of,
                    contract_chains=self._futures_contract_chains,
                    roll_lead_days=self._futures_roll_lead_days,
                )[ref]
            raise InstrumentResolutionError(
                f"unsupported InstrumentRef variant {type(ref).__name__}"
            )

        return resolve

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
        InstrumentRef's *resolved* InstrumentId (so every instrument carries its own
        venue). InstrumentRefs absent from pipeline identity are skipped — the caps
        are only as complete as the resolution.
        """
        identity = self._require_pipeline().resolved_identity_snapshot()
        instrument_ids: list[str] = [
            identity[figi].value
            for contract in self._sleeve_to_contract.values()
            for figi in contract.refs
            if figi in identity
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
            else self._instrument_id_for_ref(oi.ref)
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
