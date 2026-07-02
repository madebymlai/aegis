"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

Identity is the native ``InstrumentId`` declared by each Execution Bundle.  The
strategy never resolves symbols, FIGIs, or broker-specific aliases at runtime.

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

from typing import Any

from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_data.catalog import CatalogBackedDataPort, catalog_root, parquet_data_catalog
from aegis_runtime import DataContract, ExecutionBundle

from aegis_trader.data import (
    MarketDataPort,
    NautilusMarketData,
    raw_bar_type,
    timeframe_to_ns,
)
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    RollIntent,
    RollIntentBatch,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.startup import StartupResult
from aegis_trader.domain.types import (
    OrderIntent,
    OrderSide,
    OrderSource,
    SleeveName,
)
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    GateOutcome,
    RebalancePipeline,
    RebalanceSummary,
)
from aegis_trader.portfolio import BookStatePort, NautilusBookState
from aegis_trader.trader.book_startup import (
    BootIntent,
    BootIntentBatch,
    SubscribeQuoteTicks,
    bootstrap,
)
from aegis_trader.trader.roll_desk import RollDesk

_NS_PER_DAY: int = 86_400_000_000_000


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    risk_guard_config: RiskGuardConfig = RiskGuardConfig()
    warmup_cache_on_start: bool = False
    fill_time_in_force: TimeInForce | None = None
    """Time-in-force for submitted orders (ADR-0001, next-close execution).

    ``None`` (backtest): a plain ``MARKET`` order fills at the execution bar's
    close — the SimulatedExchange rejects session TIFs.  ``AT_THE_CLOSE``
    (live): a Market-on-Close order into the closing auction.  Set by the backtest
    runner (``backtest.py``) and the live node (``trader/node.py``) so backtest and
    live model the same fill point (the close)."""


class RebalanceStrategy(Strategy):
    """Commingled-book rebalance overlay — submits orders NEXT-CLOSE.

    Per-sleeve timeframe cadence (Slice 6):
    - When the period (day) changes, a rebalance is triggered for the
      *completed* period using the Cache-backed rolling bar window.
    - Each sleeve's bundle computes targets from its own Cache-backed bars,
      netted across sleeves, and orders are emitted only for instruments
      whose venue was open (had a Cache bar) during the completed period.
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
        # Book bar timeframe (one across sleeves); set in on_start.
        self._book_timeframe: str | None = None
        # ── Slice 8: RiskEngine guards ───────────────────────────────────
        self._risk_guard: RiskGuard = RiskGuard(config.risk_guard_config)
        # Slice 7: startup gates + global halt
        self._startup_result: StartupResult | None = None
        self._is_halted: bool = False
        # Wave B: reconciled book state behind a port (no direct cache/portfolio reads).
        self._book_state: BookStatePort | None = None
        self._market_data: MarketDataPort | None = None
        self._roll_desk: RollDesk | None = None
        # Pure cross-period analytics ledger is injected into the per-period pipeline.
        self._sleeve_ledger: SleeveLedger = SleeveLedger()
        self._pipeline: RebalancePipeline | None = None
        self._last_attribution: dict[SleeveName, float] = {}
        self._last_book_skew: float | None = None
        self._last_sleeve_weights: dict[SleeveName, float] = {}

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

    @property
    def last_attribution(self) -> dict[SleeveName, float]:
        """Last realized per-sleeve attribution, for evidence/backtest seams."""
        return dict(self._last_attribution)

    @property
    def startup_result(self) -> StartupResult | None:
        """Startup gate decision, for backtest/evidence inspection."""
        return self._startup_result

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

    def _require_book_timeframe(self) -> str:
        if self._book_timeframe is None:
            raise RuntimeError("book timeframe queried before on_start resolved it")
        return self._book_timeframe

    def _registered_instrument_ids(self) -> tuple[InstrumentId, ...]:
        # Natives only: continuous roots are materialized and subscribed through the Roll Desk.
        instrument_ids = {
            instrument_id
            for contract in self._sleeve_to_contract.values()
            for instrument_id in contract.native_instrument_ids
        }
        return tuple(sorted(instrument_ids, key=lambda instrument_id: instrument_id.value))

    def _declared_continuous_ids_by_root(self) -> dict[str, InstrumentId]:
        """Continuous-root declarations keyed by bare root."""
        declared: dict[str, InstrumentId] = {}
        for contract in self._sleeve_to_contract.values():
            continuous_ids = {
                instrument_id.symbol.value: instrument_id
                for instrument_id in contract.continuous_instrument_ids
            }
            for root in contract.futures:
                continuous_id = continuous_ids[root]
                existing = declared.setdefault(root, continuous_id)
                if existing != continuous_id:
                    raise RuntimeError(
                        f"continuous root {root!r} declared as both "
                        f"{existing.value} and {continuous_id.value}"
                    )
        return dict(sorted(declared.items()))

    def _require_roll_desk(self) -> RollDesk:
        if self._roll_desk is None:
            raise RuntimeError("roll desk queried before on_start wired it")
        return self._roll_desk

    def _build_roll_desk(self) -> RollDesk:
        return RollDesk(
            catalog_port=self._continuous_port(),
            instrument_present=lambda instrument_id: self.cache.instrument(instrument_id)
            is not None,
            declared_continuous_ids_by_root=self._declared_continuous_ids_by_root(),
        )

    def _continuous_port(self) -> CatalogBackedDataPort:
        """The catalog-backed read port the Roll Desk re-materializes through — the node's shared
        ParquetDataCatalog (the same corpus warmed via request_bars(update_catalog=True))."""
        return CatalogBackedDataPort(parquet_data_catalog(catalog_root()))

    def _fx_reference_pairs(self) -> tuple[InstrumentId, ...]:
        return tuple(
            sorted(
                (
                    instrument.id
                    for instrument in self.cache.instruments()
                    if isinstance(instrument, CurrencyPair)
                ),
                key=lambda instrument_id: instrument_id.value,
            )
        )

    # ── Nautilus lifecycle ────────────────────────────────────────────────────

    def on_start(self) -> None:
        if not self._sleeve_to_bundle:
            self.log.warning("No sleeves registered; strategy will idle.")
            return

        base_ccy = Currency.from_str(self._book.base_currency)
        self._book_state = NautilusBookState(
            portfolio=self.portfolio,
            cache=self.cache,
            base_currency=base_ccy,
            covered_instrument_ids=frozenset(self._registered_instrument_ids()),
        )
        roll_desk = self._build_roll_desk()
        self._roll_desk = roll_desk
        self._market_data = NautilusMarketData(cache=self.cache, continuous=roll_desk)

        boot = bootstrap(
            now=self.clock.utc_now(),
            book=self._book,
            sleeve_to_bundle=self._sleeve_to_bundle,
            ledger=self._sleeve_ledger,
            book_state=self._require_book_state(),
            market_data=self._require_market_data(),
            roll_desk=roll_desk,
            fx_reference_pairs=self._fx_reference_pairs(),
            warmup_cache_on_start=self.config.warmup_cache_on_start,
        )
        if isinstance(boot, Halt):
            self._halt_from_roll_intent(boot)
            return

        self._pipeline = boot.pipeline
        self._book_timeframe = boot.timeframe
        self._period_ns = timeframe_to_ns(boot.timeframe)
        self._startup_result = boot.startup_result
        self._log_startup_pass(boot.startup_result)
        instrument_ids = self._registered_instrument_ids()
        if self._apply_boot_intents(boot.intents):
            return

        names = [s.value for s in self._sleeve_to_bundle]
        self.log.info(
            f"RebalanceStrategy starting; sleeves={names}, "
            f"instrument_ids={[instrument_id.value for instrument_id in instrument_ids]}"
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

        # Drives today's offset-0 append and any in-process roll before the cadence reads the
        # series, so the rebalance window already sees the live continuous bar.
        if self._apply_roll_intents(self._require_roll_desk().on_bar(bar)):
            return

        period = self._extract_period(bar)

        # ── period-advance → rebalance the completed period ──────────────
        if self._current_period is not None and period != self._current_period:
            self._rebalance_for_period()

        self._current_period = period

    # ── internal helpers ──────────────────────────────────────────────────────

    def on_instrument(self, instrument: Instrument) -> None:
        """Forward loaded instruments to the Roll Desk relay."""
        if self._roll_desk is None:
            return
        self._apply_roll_intents(self._roll_desk.on_instrument(instrument.id))

    def _apply_boot_intents(self, intents: BootIntentBatch) -> bool:
        for intent in intents:
            if self._apply_boot_intent(intent):
                return True
        return False

    def _apply_boot_intent(self, intent: BootIntent) -> bool:
        if isinstance(intent, SubscribeQuoteTicks):
            self.subscribe_quote_ticks(intent.instrument_id)
            return False
        return self._apply_roll_intent(intent)

    def _apply_roll_intents(self, intents: RollIntentBatch) -> bool:
        for intent in intents:
            if self._apply_roll_intent(intent):
                return True
        return False

    def _apply_roll_intent(self, intent: RollIntent) -> bool:
        if isinstance(intent, SubscribeBars):
            self.subscribe_bars(raw_bar_type(intent.instrument_id, intent.timeframe))
            return False
        if isinstance(intent, UnsubscribeBars):
            self.unsubscribe_bars(raw_bar_type(intent.instrument_id, intent.timeframe))
            return False
        if isinstance(intent, RequestInstrument):
            self.request_instrument(intent.instrument_id)
            return False
        if isinstance(intent, RequestBars):
            self.request_bars(
                raw_bar_type(intent.instrument_id, intent.timeframe),
                start=intent.start,
                end=intent.end,
                update_catalog=intent.update_catalog,
            )
            return False
        if isinstance(intent, RollEvent):
            self._require_pipeline().apply_roll(intent)
            return False
        if isinstance(intent, Halt):
            self._halt_from_roll_intent(intent)
            return True
        return False

    def _halt_from_roll_intent(self, intent: Halt) -> None:
        startup_result = StartupResult(
            trading_enabled=False,
            halt_gate=intent.gate,
            halt_reason=intent.reason,
        )
        self._startup_result = startup_result
        self._is_halted = True
        self._log_startup_halt(startup_result)

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
            return

        for oi in result.orders:
            self._submit_order_intent(oi)

    def _log_startup_halt(self, result: StartupResult) -> None:
        gate = result.halt_gate.value if result.halt_gate is not None else "unknown"
        reason = result.halt_reason or "unknown startup failure"
        self.log.error(f"Startup gate FAILED: gate={gate} reason={reason}. HALTING the book.")

    def _log_startup_pass(self, result: StartupResult) -> None:
        nav = 0.0 if result.nav is None else result.nav
        cash = 0.0 if result.cash is None else result.cash
        self.log.info(f"Startup checks passed: NAV={nav:.2f}, cash={cash:.2f}")

    def _log_rebalance_summary(self, summary: RebalanceSummary) -> None:
        """Emit a structured rebalance log through Nautilus's native logger."""
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
        pipeline = self._pipeline
        if pipeline is None:
            return
        names = self._positive_risk_sleeve_names()
        weights = {name: self._last_sleeve_weights.get(name, 0.0) for name in names}
        self._last_book_skew = pipeline.realized_book_skew(weights, names)
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
        pipeline = self._pipeline
        if pipeline is None:
            return

        self._record_book_skew()

        if pipeline.observation_count < 2:
            return

        risk_shares = self._book.allocator_risk_shares()
        attribution = pipeline.attribution(risk_shares)
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

        Computes per-instrument max notionals from the current NAV, keyed by the
        native InstrumentIds declared by the loaded bundle contracts.
        """
        return self._risk_guard.risk_engine_config_dict(
            nav=nav,
            instrument_ids=[
                instrument_id.value
                for instrument_id in self._registered_instrument_ids()
            ],
        )

    # -- order submission -------------------------------------------------------

    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit.

        A continuous-root intent is a price-series signal; the order trades the real dated front
        leg the market-data port maps it to (root→front, rolling in lock-step with the data roll).
        The quantity is already a native share count (sized by the rebalancer), so it is passed
        directly to ``make_qty``.
        """
        market_data = self._require_market_data()
        execution_id = market_data.execution_instrument_id(oi.instrument_id)
        quantity = market_data.make_quantity(execution_id, oi.quantity)
        if quantity is None:
            self.log.error(
                f"Instrument not found for InstrumentId {execution_id.value}; skipping order"
            )
            return

        nt_side = NtOrderSide.BUY if oi.side == OrderSide.BUY else NtOrderSide.SELL
        kwargs: dict[str, Any] = {
            "instrument_id": execution_id,
            "order_side": nt_side,
            "quantity": quantity,
        }
        # NEXT-CLOSE (ADR-0001): backtest leaves the factory default (plain MARKET
        # fills at the bar close); paper/live carry AT_THE_CLOSE (Market-on-Close).
        if self.config.fill_time_in_force is not None:
            kwargs["time_in_force"] = self.config.fill_time_in_force
        if oi.source == OrderSource.ROLL:
            self.log.info(
                f"Roll order: {oi.side.value} {oi.quantity:.0f} {execution_id.value}"
            )
        order = self.order_factory.market(**kwargs)
        self.submit_order(order)
