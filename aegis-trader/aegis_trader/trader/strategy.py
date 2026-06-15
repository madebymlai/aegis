"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

Slice 3: FIGI→InstrumentId resolution via the Security Master (OpenFIGI +
bounded exchange-code table).  A FIGI→InstrumentId bimap is built at
``on_start``; netting stays in FIGI space, resolution to venue-specific
InstrumentIds only at the execution edge (order submission).

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

import numpy as np
import pandas as pd
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_runtime import DataContract, ExecutionBundle, MarketDataBundle
from aegis_runtime.currency import major_currency

from aegis_trader.bundles.provenance import CapProvenanceError, check_cap_provenance
from aegis_trader.data import MarketDataPort, NautilusMarketData
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import IntegrityReport, check_account_integrity
from aegis_trader.domain.rebalancer import rebalance_plan
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.types import Figi, OrderIntent, OrderSide, SleeveName
from aegis_trader.execution.figi_resolver import (
    FigiInstrumentResolver,
    FigiResolutionError,
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


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    figi_resolver: FigiInstrumentResolver | None = None
    risk_guard_config: RiskGuardConfig = RiskGuardConfig()
    obs_port: ObservabilityPort | None = None
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
        self._instr_to_figi: dict[str, str] = {}  # InstrumentId.value → FIGI (bimap inverse)
        # ── bar buffers & cadence state ──────────────────────────────────
        self._bars_buffer: dict[InstrumentId, list[Bar]] = {}
        self._current_period: int | None = None
        self._period_fresh_figis: set[str] = set()
        # ── Slice 3: FIGI bimap ──────────────────────────────────────────
        self._figi_bimap: dict[str, InstrumentId] = {}
        self._figi_resolver: FigiInstrumentResolver = (
            config.figi_resolver if config.figi_resolver is not None
            else FigiInstrumentResolver()
        )
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
        self._last_sleeve_weights: dict[SleeveName, float] = {}
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
        all_figis: set[str] = set()
        for bundle in self._sleeve_to_bundle.values():
            all_figis.update(bundle.contract.figis)

        # Slice 3: resolve FIGIs to venue-native InstrumentIds via the Security
        # Master bimap.  The bimap is the SINGLE source of truth for instrument
        # identity - every subscription, bar buffer, sizing read, order, and risk
        # cap keys off it.  (A stub bimap may be injected by e2e tests.)
        if not self._figi_bimap:
            self._figi_bimap = self._resolve_bimap(all_figis)

        # Subscribe to bars on the RESOLVED InstrumentId and build the inverse
        # (InstrumentId -> FIGI) map used for position lookups.
        for figi in all_figis:
            instr_id = self._figi_to_instr_id(figi)
            self._instr_to_figi[instr_id.value] = figi
            self.subscribe_bars(
                BarType.from_str(f"{instr_id.value}-1-DAY-LAST-EXTERNAL")
            )

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

    @staticmethod
    def _extract_period(bar: Bar) -> int:
        """Extract the day period from *bar*'s event timestamp.

        For 1D bars the period is the calendar day; this generalises to
        any fixed-width bar by replacing the divisor with the bar step.
        """
        return bar.ts_event // _NS_PER_DAY

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

            # Assemble per-sleeve close-price series
            sleeve_closes: dict[str, pd.DataFrame] = {}
            sleeve_ok = True
            for figi in contract.figis:
                instr_id = self._figi_to_instr_id(figi)
                buf = self._bars_buffer.get(instr_id, [])
                if len(buf) < needed:
                    sleeve_ok = False
                    break
                close_series = _bars_to_close_series(buf, figi)
                sleeve_closes[figi] = close_series

            if not sleeve_ok or not sleeve_closes:
                continue

            # Combine all FIGI close series for this sleeve into one DataFrame
            if len(sleeve_closes) == 1:
                close_df = next(iter(sleeve_closes.values()))
            else:
                close_df = pd.concat(sleeve_closes.values(), axis=1)

            bundle_data = MarketDataBundle({"Close": close_df})
            fx_series = self._fx_series_for(contract, close_df.index)
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
            if o.figi.value in self._period_fresh_figis
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
                        Figi(str(figi)): float(weight)
                        for figi, weight in target_df.iloc[-1].to_dict().items()
                    }
                    for name, target_df in pending.items()
                },
                closes=dict(prices),
            )
        )

        # Calendar-aware: only emit orders for FIGIs with a fresh bar
        for oi in orders:
            if oi.figi.value not in self._period_fresh_figis:
                self.log.info(
                    f"Skipping {oi.side.value} {oi.quantity:.0f} "
                    f"{oi.figi.value}: venue closed this period"
                )
                continue
            self._submit_order_intent(oi)

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

    def on_stop(self) -> None:
        """Compute and log per-sleeve P&L attribution at end of run.

        Decomposes the realized-weight book P&L across sleeves by their
        budget-scaled target share (compute_sleeve_attribution); needs at
        least two recorded rebalance periods.
        """
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

    def _figi_to_instr_id(self, figi: str) -> InstrumentId:
        """Resolve a FIGI to a venue-specific InstrumentId.

        Fails closed (raises) when the FIGI was not resolved: the book never
        acts on an unidentified instrument, and never reconstructs identity by
        parsing strings (ADR-0002).
        """
        instr_id = self._figi_bimap.get(figi)
        if instr_id is None:
            raise FigiResolutionError(
                f"FIGI {figi!r} is not in the resolved bimap; refusing to act "
                f"on an unidentified instrument"
            )
        return instr_id

    def _resolve_bimap(self, figis: set[str]) -> dict[str, InstrumentId]:
        """Resolve *figis* to a bimap via the Security Master."""
        return self._figi_resolver.resolve(figis)

    def _collect_sizing_params(
        self,
    ) -> tuple[dict[Figi, InstrumentSizing], dict[str, float], dict[Figi, float]]:
        """Gather per-FIGI instrument metadata, FX rates, and latest close
        prices from Nautilus for sizing.

        Returns three dicts keyed by :class:`Figi` (instrument_metas/prices) or
        currency (fx_rates).  An instrument that cannot be resolved from the
        cache is silently omitted (the rebalancer will fall back to raw
        notional for it).
        """
        instrument_metas: dict[Figi, InstrumentSizing] = {}
        prices: dict[Figi, float] = {}
        currencies: set[str] = set()

        # Collect all FIGIs from all sleeves
        all_figis: set[str] = set()
        for bundle in self._sleeve_to_bundle.values():
            all_figis.update(bundle.contract.figis)

        for figi_str in all_figis:
            instr_id = self._figi_to_instr_id(figi_str)
            sizing = self._require_market_data().instrument_sizing(instr_id)
            if sizing is None:
                continue

            figi = Figi(figi_str)
            instrument_metas[figi] = sizing

            buf = self._bars_buffer.get(instr_id)
            if buf:
                prices[figi] = float(buf[-1].close.as_double())

            currencies.add(sizing.currency)

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
            for figi in contract.figis
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
        instr_id = self._figi_to_instr_id(oi.figi.value)
        quantity = self._require_market_data().make_quantity(instr_id, oi.quantity)
        if quantity is None:
            self.log.error(
                f"Instrument not found for FIGI {oi.figi.value}; skipping order"
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
        order = self.order_factory.market(**kwargs)
        self.submit_order(order)


def current_drawdown(nav_history: list[float], current_nav: float) -> float:
    """Return current drawdown from the running NAV peak as a fraction."""
    if not np.isfinite(current_nav):
        raise ValueError("current NAV must be finite")
    peak = max([float(current_nav), *(float(nav) for nav in nav_history)])
    if peak <= 0.0:
        return 0.0
    drawdown = 1.0 - float(current_nav) / peak
    return min(max(drawdown, 0.0), 1.0)


def _bars_to_close_series(
    bars: list[Bar], figi: str,
) -> pd.DataFrame:
    """Convert buffered bars into a single-column close-price DataFrame keyed by *figi*."""
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [float(b.close.as_double()) for b in bars]
    return pd.DataFrame({figi: values}, index=index)


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
