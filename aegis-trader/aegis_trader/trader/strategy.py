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

The strategy logs every ``OrderDenied`` event so operators can trace rejected
orders.

Per-Sleeve cadence (aegis-rd-9qkr):
- Each Sleeve rebalances off bar-close at its own DataContract.timeframe;
  its clock advances only on bars of streams it consumes.
- Debounced: one recomputation per completed Sleeve period; same-timestamp
  due transitions coalesce into one deterministic Book re-net.
- Calendar-aware: orders emitted only for instruments whose venue is open
  (had a fresh bar during the relevant Sleeve period).
- Drift is evaluated on every due update even on an unchanged target.

Slice 7 - reconciliation (integrity-halt): an account-integrity check at
startup (cache health, account ID, NAV/cash consistency) halts the book
globally on failure.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any, assert_never

from nautilus_trader.common.component import TimeEvent
from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar, BarType, MarkPriceUpdate, QuoteTick
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver
from aegis_data.storage import Catalog

from aegis_trader.bundles.book import AssembledBook
from aegis_trader.data import (
    MarketDataPort,
    NautilusMarketData,
)
from aegis_trader.domain.book_config import BookConfig
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
    DueSleeve,
    GateOutcome,
    RebalancePipeline,
    RebalanceRequest,
    RebalanceSummary,
)
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.portfolio import BookStatePort, NautilusBookState
from aegis_trader.trader.book_startup import (
    BootIntent,
    BootIntentBatch,
    SubscribeQuoteTicks,
    bootstrap,
)
from aegis_trader.trader.book_market_clock import BookMarketClock
from aegis_trader.trader.bar_capture import BarCapture
from aegis_trader.trader.roll_desk import RollDesk
from aegis_trader.trader.startup_fast_forward import (
    HistoryRequest,
    Ready,
    RECOVERY_TOPIC,
    Recovering,
    RecoveryUpdate,
    StartupFastForward,
)

_BAR_CAPTURE_TIMER = "aegis-bar-capture"
_BAR_CAPTURE_INTERVAL = timedelta(hours=1)


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    warmup_cache_on_start: bool = False
    capture_bars: bool = False
    """Whether arriving Bars are persisted to the Catalog as they are observed.

    A durable write is its own decision, not a corollary of warming the cache.
    Live captures because the Catalog is where it reads history back from: a
    Bar it observed and a Bar a provider filled are the same record in the same
    dataset, with nothing marking which arrived how.  A session that runs on
    for months is reading its own earlier days back out of the Catalog, and it
    can only do that if it put them there.  Backtest replays a Catalog it must
    not write back into."""

    fill_time_in_force: TimeInForce | None = None
    """Time-in-force for submitted orders (ADR-0001, next-close execution).

    ``None`` (backtest): a plain ``MARKET`` order fills at the execution bar's
    close — the SimulatedExchange rejects session TIFs.  ``AT_THE_CLOSE``
    (live): a Market-on-Close order into the closing auction.  Set by the backtest
    runner (``backtest.py``) and the live node (``trader/node.py``) so backtest and
    live model the same fill point (the close)."""


class BookConfigMismatchError(ValueError):
    """An assembled Book does not match the Strategy's configured Book Config."""


class RebalanceStrategy(Strategy):
    """Commingled-book rebalance overlay — submits orders NEXT-CLOSE.

    Per-Sleeve timeframe cadence (aegis-rd-9qkr):
    - When a Sleeve's own period completes, that Sleeve recomputes from the
      Cache-backed completed-period window; every other Sleeve retains its
      latest valid target.
    - Due transitions at one event timestamp coalesce into one re-net that
      allocates and nets the whole retained Book, and orders are emitted only
      for instruments whose venue was open during the relevant Sleeve period.
    """

    def __init__(
        self,
        config: RebalanceStrategyConfig,
        *,
        arrays: SleeveArrays,
        catalog: Catalog,
        bar_type_resolver: RawBarTypeResolver = DeclaredMarkingResolver(),
    ) -> None:
        super().__init__(config)
        # The one raw bar-type resolution seam (aegis-rd-tggo.1): every
        # subscribe/unsubscribe/request and cache read resolves through it.
        self._bar_type_resolver = bar_type_resolver
        self._catalog_port = CatalogBackedDataPort(
            catalog,
            resolver=bar_type_resolver,
        )
        self._bar_capture = (
            BarCapture(self._catalog_port.raw_bars) if config.capture_bars else None
        )
        self._arrays = arrays
        self._assembled_book: AssembledBook | None = None
        self._timeframe_by_bar_type: dict[BarType, str] = {}
        self._book_market_clock: BookMarketClock | None = None
        self._pending_due_timestamp: int | None = None
        # Slice 7: startup gates + global halt
        self._startup_result: StartupResult | None = None
        self._is_halted: bool = False
        # Wave B: reconciled book state behind a port (no direct cache/portfolio reads).
        self._book_state: BookStatePort | None = None
        self._market_data: MarketDataPort | None = None
        self._roll_desk: RollDesk | None = None
        # Pure cross-period analytics ledger is injected into the per-period
        # pipeline; built in ``register_book`` where the Book's derived
        # analytics horizon first becomes known (aegis-rd-cy7l).
        self._sleeve_ledger: SleeveLedger | None = None
        self._pipeline: RebalancePipeline | None = None
        self._fast_forward: StartupFastForward | None = None
        self._recovery_ready: Ready | None = None
        self._is_recovering = False
        self._book_activity: int | None = None
        self._stream_watermarks: dict[BarType, int] = {}
        self._last_attribution: dict[SleeveName, float] = {}
        self._last_book_skew: float | None = None
        self._last_sleeve_weights: dict[SleeveName, float] = {}

    # ── public API ────────────────────────────────────────────────────────────

    def register_book(self, book: AssembledBook) -> None:
        """Register the one validated book this strategy is configured to trade."""
        if book.config != self.config.book:
            raise BookConfigMismatchError(
                "assembled Book Config differs from the strategy's configured Book Config"
            )
        self._assembled_book = book
        self._sleeve_ledger = SleeveLedger(horizon=book.analytics_horizon)

    @property
    def last_attribution(self) -> dict[SleeveName, float]:
        """Last realized per-sleeve attribution, for evidence/backtest seams."""
        return dict(self._last_attribution)

    @property
    def startup_result(self) -> StartupResult | None:
        """Startup gate decision, for backtest/evidence inspection."""
        return self._startup_result

    @property
    def book_activity(self) -> int | None:
        """Latest fully folded market event time across recovery and live."""
        return self._book_activity

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

    def _require_book_market_clock(self) -> BookMarketClock:
        if self._book_market_clock is None:
            raise RuntimeError("Book Market Clock queried before on_start wired it")
        return self._book_market_clock

    def _require_assembled_book(self) -> AssembledBook:
        if self._assembled_book is None:
            raise RuntimeError("assembled book queried before registration")
        return self._assembled_book

    def _require_roll_desk(self) -> RollDesk:
        if self._roll_desk is None:
            raise RuntimeError("roll desk queried before on_start wired it")
        return self._roll_desk

    def _require_sleeve_ledger(self) -> SleeveLedger:
        if self._sleeve_ledger is None:
            raise RuntimeError(
                "sleeve ledger queried before book registration built it"
            )
        return self._sleeve_ledger

    def _build_roll_desk(self) -> RollDesk:
        # Operational dependencies only: bundle contracts are unioned into coherent
        # declarations by book startup, which hands them to RollDesk.start.
        return RollDesk(
            catalog_port=self._continuous_port(),
            instrument_present=lambda instrument_id: (
                self.cache.instrument(instrument_id) is not None
            ),
        )

    def _continuous_port(self) -> CatalogBackedDataPort:
        """The catalog-backed read port the Roll Desk re-materializes through — the node's shared
        Catalog (the same data warmed through the provider-backed port)."""
        return self._catalog_port

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
        if self._assembled_book is None:
            self.log.warning("No book registered; strategy will idle.")
            return

        assembled_book = self._require_assembled_book()
        if self._bar_capture is not None:
            self.clock.set_timer(
                _BAR_CAPTURE_TIMER,
                _BAR_CAPTURE_INTERVAL,
                callback=self._on_bar_capture_timer,
            )
        base_ccy = Currency.from_str(assembled_book.config.base_currency)
        self._book_state = NautilusBookState(
            portfolio=self.portfolio,
            cache=self.cache,
            base_currency=base_ccy,
            covered_instrument_ids=frozenset(assembled_book.loadable_instrument_ids),
        )
        roll_desk = self._build_roll_desk()
        self._roll_desk = roll_desk
        self._market_data = NautilusMarketData(
            cache=self.cache,
            continuous=roll_desk,
            resolver=self._bar_type_resolver,
        )

        pipeline = RebalancePipeline(
            book_state=self._require_book_state(),
            market_data=self._require_market_data(),
            book=assembled_book,
            ledger=self._require_sleeve_ledger(),
            arrays=self._arrays,
        )
        self._pipeline = pipeline
        self._build_mark_timeframe_index(assembled_book)
        self._book_market_clock = BookMarketClock(
            book=assembled_book,
            bar_type_resolver=self._bar_type_resolver,
        )
        if self.config.warmup_cache_on_start:
            self._fast_forward = StartupFastForward(
                book=assembled_book,
                pipeline=pipeline,
                roll_desk=roll_desk,
                bar_type_resolver=self._bar_type_resolver,
                book_market_clock=self._require_book_market_clock(),
                fx_reference_pairs=self._fx_reference_pairs(),
            )
            self._is_recovering = True
            self._handle_recovery(
                self._fast_forward.begin(through=self.clock.utc_now())
            )
            return

        boot = bootstrap(
            now=self.clock.utc_now(),
            book=assembled_book,
            pipeline=pipeline,
            roll_desk=roll_desk,
            fx_reference_pairs=self._fx_reference_pairs(),
            warmup_cache_on_start=False,
        )
        if isinstance(boot, Halt):
            self._halt_from_roll_intent(boot)
            return

        self._startup_result = boot.startup_result
        self._log_startup_pass(boot.startup_result)
        instrument_ids = assembled_book.loadable_instrument_ids
        if self._apply_boot_intents(boot.intents):
            return

        names = [name.value for name in assembled_book.sleeves]
        self.log.info(
            f"RebalanceStrategy starting; sleeves={names}, "
            f"instrument_ids={[instrument_id.value for instrument_id in instrument_ids]}"
        )

    def on_historical_data(self, data: Data) -> None:
        """Relay Nautilus historical deliveries into startup fast-forward."""
        if self._fast_forward is None or not self._is_recovering:
            return
        self._handle_recovery(self._fast_forward.receive_history(data))

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
        self.cache.set_mark_xrate(
            instrument.base_currency, instrument.quote_currency, mid
        )

    def on_bar(self, bar: Bar) -> None:
        """Advance the consuming Sleeves' clocks and coalesce due transitions.

        Each Sleeve debounces to one recomputation per completed period of its
        own cadence.  Due transitions at one event timestamp accumulate and a
        native time alert (1ns after the trigger, firing once every same-
        timestamp bar has been processed) flushes them into one deterministic
        Book re-net -- orders still submit within the trigger close, preserving
        next-close execution and one-bar lag per cadence (aegis-rd-9qkr.3).
        """
        if self._assembled_book is None or self._is_halted or self._is_recovering:
            return
        if self._recovery_ready is not None:
            admission = self._recovery_ready.admit_live(bar)
            if isinstance(admission, Halt):
                self._halt_from_roll_intent(admission)
                return
            if not admission:
                return
        watermark = self._stream_watermarks.get(bar.bar_type)
        if watermark is not None and bar.ts_event <= watermark:
            return

        if self._bar_capture is not None:
            # Buffer only. One stream's arrival says nothing about whether its
            # peers can still deliver. The clock timer replaces each stream's
            # exact Catalog interval, and the roll probe reads that extent.
            self._bar_capture.observe(bar)

        # Drives today's offset-0 append and any in-process roll before the cadence reads the
        # series, so the rebalance window already sees the live continuous bar.
        continuous_id = self._require_roll_desk().continuous_id(
            bar.bar_type.instrument_id
        )
        if self._apply_roll_intents(self._require_roll_desk().on_bar(bar)):
            return
        if continuous_id is None and bar.bar_type not in self._timeframe_by_bar_type:
            # Candidate legs are subscribed so the roll probe can read and
            # capture them. Until one becomes the front, they are not Book
            # observations and must not advance a Sleeve clock or mark.
            self._stream_watermarks[bar.bar_type] = bar.ts_event
            return

        derived_mark = self._resolve_derived_mark(bar)
        if derived_mark is not None:
            self._publish_mark(*derived_mark, bar=bar)
        self._record_market_observation(bar, derived_mark, continuous_id)

        market_clock = self._require_book_market_clock()
        market_clock.advance(
            bar.bar_type,
            bar.ts_event,
            continuous_id=continuous_id,
        )
        if market_clock.has_pending_due:
            self._schedule_re_net(bar.ts_event)
        self._stream_watermarks[bar.bar_type] = bar.ts_event
        self._book_activity = max(self._book_activity or bar.ts_event, bar.ts_event)

    def _build_mark_timeframe_index(self, book: AssembledBook) -> None:
        """Index native mark bars by the Market-Data Stream timeframe they complete."""
        self._timeframe_by_bar_type = {
            bar_type: stream.timeframe
            for streams in book.sleeve_streams.values()
            for stream in streams
            for bar_type in self._mark_bars(stream.instrument_id, stream.timeframe)
        }

    def _schedule_re_net(self, trigger_timestamp_ns: int) -> None:
        """One alert per due-transition cluster: 1ns after the trigger event,
        so every same-timestamp bar routes before the Book re-nets once."""
        if self._pending_due_timestamp == trigger_timestamp_ns:
            return
        self._pending_due_timestamp = trigger_timestamp_ns
        self.clock.set_time_alert_ns(
            f"re-net-{trigger_timestamp_ns}",
            trigger_timestamp_ns + 1,
            callback=self._on_re_net_alert,
        )

    def _on_re_net_alert(self, event: TimeEvent) -> None:
        due = self._require_book_market_clock().drain()
        self._pending_due_timestamp = None
        if not due or self._is_halted:
            return
        self._rebalance_due_sleeves(due, event.ts_event)

    def _on_bar_capture_timer(self, event: TimeEvent) -> None:
        if self._bar_capture is not None:
            self._bar_capture.advance_clock(event.ts_event)

    def _record_market_observation(
        self,
        bar: Bar,
        derived_mark: tuple[InstrumentId, float] | None,
        continuous_id: InstrumentId | None = None,
    ) -> None:
        """Record the advancing stream's mark as a full-Book observation --
        retained Sleeves stay marked whether or not anything is due."""
        if self._pipeline is None:
            return
        if derived_mark is not None:
            instrument_id, mark = derived_mark
        else:
            instrument_id = continuous_id or self._observed_instrument(bar)
            mark = float(bar.close)
        self._pipeline.record_market_observation(bar.ts_event, {instrument_id: mark})

    def _observed_instrument(self, bar: Bar) -> InstrumentId:
        """The identity a bar marks: a dated front leg marks its continuous
        root (targets and ledger closes key the root), a cash bar itself."""
        continuous_id = self._require_roll_desk().continuous_id(
            bar.bar_type.instrument_id
        )
        if continuous_id is not None:
            return continuous_id
        return bar.bar_type.instrument_id

    # ── internal helpers ──────────────────────────────────────────────────────

    def _handle_recovery(self, update: RecoveryUpdate) -> None:
        self.msgbus.publish(RECOVERY_TOPIC, update, external_pub=False)
        if isinstance(update, Halt):
            self._halt_from_roll_intent(update)
            return
        if isinstance(update, Recovering):
            for request in update.requests:
                self._request_recovery_history(request)
            return
        if isinstance(update, Ready):
            self._recovery_ready = update
            self._startup_result = update.startup_result
            self._log_startup_pass(update.startup_result)
            self._stream_watermarks.update(
                (bar.bar_type, bar.ts_event) for bar in update.boundary_bars
            )
            self._book_activity = update.book_activity
            if self._apply_boot_intents(update.intents):
                return
            self._is_recovering = False
            assembled_book = self._require_assembled_book()
            names = [name.value for name in assembled_book.sleeves]
            instrument_ids = assembled_book.loadable_instrument_ids
            self.log.info(
                f"RebalanceStrategy starting; sleeves={names}, "
                f"instrument_ids={[item.value for item in instrument_ids]}"
            )
            return
        assert_never(update)

    def _request_recovery_history(self, request: HistoryRequest) -> None:
        fast_forward = self._fast_forward
        if fast_forward is None:
            raise RuntimeError("recovery history requested without fast-forward")

        def completed(_request_id: object) -> None:
            self._handle_recovery(fast_forward.history_loaded(request.key))

        self.request_bars(
            request.bar_type,
            start=request.start,
            end=request.end,
            callback=completed,
            update_catalog=request.update_catalog,
        )

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
            for bar_type in self._mark_bars(intent.instrument_id, intent.timeframe):
                self.subscribe_bars(bar_type)
                if self._bar_capture is not None:
                    self._bar_capture.subscribe(
                        bar_type,
                        at_ns=self.clock.timestamp_ns(),
                    )
            return False
        if isinstance(intent, UnsubscribeBars):
            for bar_type in self._mark_bars(intent.instrument_id, intent.timeframe):
                if self._bar_capture is not None:
                    self._bar_capture.unsubscribe(
                        bar_type,
                        at_ns=self.clock.timestamp_ns(),
                    )
                self.unsubscribe_bars(bar_type)
            return False
        if isinstance(intent, RequestInstrument):
            self.request_instrument(intent.instrument_id)
            return False
        if isinstance(intent, RequestBars):
            for bar_type in self._mark_bars(intent.instrument_id, intent.timeframe):
                self.request_bars(
                    bar_type,
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
        assert_never(intent)

    def _mark_bars(
        self, instrument_id: InstrumentId, timeframe: str
    ) -> tuple[BarType, ...]:
        return self._bar_type_resolver.resolve(instrument_id, timeframe).mark_bars

    def _resolve_derived_mark(self, bar: Bar) -> tuple[InstrumentId, float] | None:
        """The quote-marked mid mark a bar completes, or ``None``.

        The one marking derivation research and live share (aegis-rd-tggo.3/.5):
        ``reference_price = (bid + ask) / 2`` over the leg's own BID/ASK bars.
        Resolution follows the bar's own stream, never a Book-wide timeframe.
        A bar-marked leg derives nothing — its bar close is the native valuation.
        """
        timeframe = self._timeframe_by_bar_type.get(bar.bar_type)
        if timeframe is None:
            return None
        marking = self._bar_type_resolver.resolve(bar.bar_type.instrument_id, timeframe)
        mark = marking.derived_mark(
            {bar_type: self.cache.bar(bar_type) for bar_type in marking.mark_bars}
        )
        if mark is None:
            return None
        return (marking.instrument_id, mark)

    def _publish_mark(self, instrument_id: InstrumentId, mark: float, bar: Bar) -> None:
        """Hand a derived mark to the Portfolio exactly as the data engine
        would deliver a vendor mark (cache + the mark-prices topic)."""
        update = MarkPriceUpdate(
            instrument_id=instrument_id,
            value=mark,
            ts_event=bar.ts_event,
            ts_init=bar.ts_init,
        )
        self.cache.add_mark_price(update)
        # The data engine's own mark-price delivery topic: the Portfolio
        # (use_mark_prices) subscribes to it in backtest and live alike.
        self.msgbus.publish(
            topic=f"data.mark_prices.{instrument_id.venue}.{instrument_id.symbol}",
            msg=update,
        )

    def _halt_from_roll_intent(self, intent: Halt) -> None:
        startup_result = StartupResult(
            trading_enabled=False,
            halt_gate=intent.gate,
            halt_reason=intent.reason,
        )
        self._startup_result = startup_result
        self._is_halted = True
        self._log_startup_halt(startup_result)

    def _rebalance_due_sleeves(
        self,
        due: tuple[DueSleeve, ...],
        timestamp_ns: int,
    ) -> None:
        """Delegate the coalesced due set to RebalancePipeline as one re-net."""
        pipeline = self._require_pipeline()
        result = pipeline.rebalance(
            RebalanceRequest(
                due=due,
                timestamp_ns=timestamp_ns,
            )
        )
        self._last_sleeve_weights = pipeline.last_sleeve_weights
        for failure in result.sleeve_failures:
            self.log.error(
                f"Sleeve compute FAILED: sleeve={failure.sleeve} "
                f"reason={failure.reason}. Sleeve holds this period."
            )
        if result.summary.gate_outcome == GateOutcome.ERROR:
            self._log_rebalance_summary(result.summary)
            self._is_halted = True
            reason = result.halt_reason or "rebalance gate failed"
            self.log.error(f"Rebalance gate FAILED: {reason}. HALTING the book.")
            return
        if result.summary.num_sleeves == 0:
            return

        self._log_rebalance_summary(result.summary)
        self._submit_order_intents(result.orders)

    def _log_startup_halt(self, result: StartupResult) -> None:
        gate = result.halt_gate.value if result.halt_gate is not None else "unknown"
        reason = result.halt_reason or "unknown startup failure"
        self.log.error(
            f"Startup gate FAILED: gate={gate} reason={reason}. HALTING the book."
        )

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
        config = self._require_assembled_book().config
        risk_shares = config.allocator_risk_shares()
        return tuple(
            sleeve.name for sleeve in config.sleeves if risk_shares[sleeve.name] > 0
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
        if self._bar_capture is not None:
            self._bar_capture.advance_clock(self.clock.timestamp_ns())
            if _BAR_CAPTURE_TIMER in self.clock.timer_names:
                self.clock.cancel_timer(_BAR_CAPTURE_TIMER)

        pipeline = self._pipeline
        if pipeline is None:
            return

        self._record_book_skew()

        if pipeline.observation_count < 2:
            return

        risk_shares = self._require_assembled_book().config.allocator_risk_shares()
        attribution = pipeline.attribution(risk_shares)
        self._last_attribution = attribution

        if attribution:
            total_book_pnl = sum(attribution.values())
            parts = ", ".join(f"{s.value}={pnl:.2f}" for s, pnl in attribution.items())
            self.log.info(
                f"Per-sleeve P&L attribution: {parts} (book total={total_book_pnl:.2f})"
            )

    # -- RiskEngine callbacks ---------------------------------------------------

    def on_order_denied(self, event: OrderDenied) -> None:
        """Log every order denial from the RiskEngine.

        A denial means the intended trade did not happen; preserve the engine's
        reason verbatim for operator diagnosis.
        """
        self.log.error(
            f"OrderDenied: instrument={event.instrument_id!r} "
            f"client_order_id={event.client_order_id!r} "
            f"reason={event.reason!r}"
        )

    # -- order submission -------------------------------------------------------

    def _submit_order_intents(self, intents: Sequence[OrderIntent]) -> None:
        """Materialize every intent before submitting any order; halt on a gap."""
        try:
            orders = tuple(self._materialize_order_intent(intent) for intent in intents)
        except ValueError as exc:
            self._is_halted = True
            self.log.error(f"Order materialization FAILED: {exc}. HALTING the book.")
            return
        for order in orders:
            self.submit_order(order)

    def _materialize_order_intent(self, oi: OrderIntent) -> Any:
        """Translate a domain OrderIntent into a venue-valid Nautilus MARKET order.

        A continuous-root intent is a price-series signal; the order trades the real dated front
        leg the market-data port maps it to (root→front, rolling in lock-step with the data roll).
        The quantity is already a native share count (sized by the rebalancer), so it is passed
        directly to ``make_qty``.
        """
        market_data = self._require_market_data()
        execution_id = market_data.execution_instrument_id(oi.instrument_id)
        quantity = market_data.make_quantity(execution_id, oi.quantity)
        if quantity is None:
            raise ValueError(
                f"instrument not found for InstrumentId {execution_id.value}"
            )

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
        return self.order_factory.market(**kwargs)
