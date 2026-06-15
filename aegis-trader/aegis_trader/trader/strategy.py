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

Slice 7 — reconciliation (integrity-halt + quarantine):
- Account-integrity check at startup: cache health, account ID, NAV/cash
  consistency.  A failed check halts the book globally.
- Unknown held positions (broker positions for FIGIs not in any sleeve
  contract) are quarantined: included in the gate but never auto-traded,
  logged as alerts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_runtime import DataContract, ExecutionBundle, MarketDataBundle

from aegis_trader.domain.attribution import compute_sleeve_attribution
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.integrity import IntegrityReport, check_account_integrity
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.types import OrderIntent, OrderSide, RebalanceResult, SleeveName
from aegis_trader.execution.figi_resolver import FigiInstrumentResolver
from aegis_trader.observability.port import (
    GateOutcome,
    ObservabilityPort,
    RebalanceSummary,
)

_NS_PER_DAY: int = 86_400_000_000_000


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    figi_resolver: FigiInstrumentResolver | None = None
    risk_guard_config: RiskGuardConfig = RiskGuardConfig()
    obs_port: ObservabilityPort | None = None


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

    Backward-compatible with the Slice 1 single-sleeve ``_bundle`` attribute
    — setting it directly is converted to the new sleeve-registry API in
    ``on_start``.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._book: BookConfig = config.book
        self._bundle: ExecutionBundle | None = None  # backward compat (Slice 1)
        self._contract: DataContract | None = None  # backward compat
        # ── Slice 6 sleeve registry ──────────────────────────────────────
        self._sleeve_to_bundle: dict[SleeveName, ExecutionBundle] = {}
        self._sleeve_to_contract: dict[SleeveName, DataContract] = {}
        self._figi_to_venue: dict[str, str] = {}
        self._instr_to_figi: dict[str, str] = {}  # "FIGI.VENUE" → FIGI
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
        # ── Slice 7: integrity + quarantine ──────────────────────────────
        self._integrity_report: IntegrityReport | None = None
        self._is_halted: bool = False
        # ── Slice 9: observability + attribution ─────────────────────────
        self._obs_port: ObservabilityPort | None = config.obs_port
        self._sleeve_target_history: dict[SleeveName, list[pd.DataFrame]] = {}
        self._close_history: dict[str, list[float]] = {}  # FIGI → list of closes

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

    # ── Nautilus lifecycle ────────────────────────────────────────────────────

    def on_start(self) -> None:
        # Backward compat: Slice 1 single-sleeve via _bundle attribute
        if self._bundle is not None and not self._sleeve_to_bundle:
            sleeve_name = self._book.sleeves[0].name
            self._sleeve_to_bundle[sleeve_name] = self._bundle
            self._sleeve_to_contract[sleeve_name] = self._bundle.contract

        if not self._sleeve_to_bundle:
            self.log.warning("No sleeves registered; strategy will idle.")
            return

        # ── Slice 7: account-integrity check at startup ──────────────────
        venue = Venue(self._book.default_venue)
        try:
            equity_map = self.portfolio.equity(venue=venue)
            base_ccy = Currency.from_str(self._book.base_currency)
            nav = float(equity_map.get(base_ccy, Money(0, base_ccy)).as_double())

            # Total cash balance from the account state
            cash = 0.0
            account_state = self.portfolio.account(venue=venue)
            if account_state is not None:
                balances = account_state.balances()
                bal = balances.get(base_ccy)
                if bal is not None:
                    cash = float(bal.total.as_double())
        except Exception as exc:
            self.log.error(
                f"Failed to query portfolio for integrity check: {exc}. "
                f"Marking NAV/cash as zero."
            )
            nav = 0.0
            cash = 0.0

        cache_healthy = len(self.cache.instruments()) > 0
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
                self._obs_port.alert_halt(self._integrity_report.reason)
            return

        self.log.info(f"Integrity check passed: NAV={nav:.2f}, cash={cash:.2f}")

        # ── Slice 9: initialise attribution trackers ────────────────────
        for sleeve in self._book.sleeves:
            self._sleeve_target_history[sleeve.name] = []

        # Build FIGI → venue map from sleeve configs
        for sleeve in self._book.sleeves:
            venue = sleeve.venue or self._book.default_venue
            bundle = self._sleeve_to_bundle.get(sleeve.name)
            if bundle is None:
                continue
            for figi in bundle.contract.figis:
                self._figi_to_venue[figi] = venue

        # Collect all unique FIGIs across all sleeves
        all_figis: set[str] = set()
        for bundle in self._sleeve_to_bundle.values():
            all_figis.update(bundle.contract.figis)

        # Slice 3: resolve FIGIs via the Security Master bimap.
        # Skip resolution if a stub bimap was injected (e2e tests).
        if not self._figi_bimap:
            self._figi_bimap = self._resolve_bimap(all_figis)

        # Subscribe to bars for all unique FIGI+venue combinations
        seen: set[str] = set()
        for name, bundle in self._sleeve_to_bundle.items():
            for figi in bundle.contract.figis:
                venue = self._figi_to_venue[figi]
                instr_id_str = f"{figi}.{venue}"
                if instr_id_str in seen:
                    continue
                seen.add(instr_id_str)
                self._instr_to_figi[instr_id_str] = figi
                bar_type = BarType.from_str(
                    f"{instr_id_str}-1-DAY-LAST-EXTERNAL"
                )
                self.subscribe_bars(bar_type)

        names = [s.value for s in self._sleeve_to_bundle]
        self.log.info(
            f"RebalanceStrategy starting; sleeves={names}, "
            f"figi_venue_map={self._figi_to_venue}"
        )

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

        Slice 7: collects held positions (broker positions for FIGIs not in any
        sleeve contract) and passes them to the rebalancer for quarantine;
        quarantined FIGIs are logged as alerts.
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
                venue = self._figi_to_venue.get(figi, self._book.default_venue)
                instr_id = InstrumentId.from_str(f"{figi}.{venue}")
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
            target = bundle.compute_weights(bundle_data)
            pending[sleeve.name] = target

        if not pending:
            return

        # Net all sleeve targets and submit
        venue = Venue(self._book.default_venue)
        equity_map = self.portfolio.equity(venue=venue)
        base_ccy = Currency.from_str(self._book.base_currency)
        nav = float(equity_map[base_ccy].as_double())

        instrument_metas, fx_rates, prices = self._collect_sizing_params(venue)
        held_positions = self._collect_held_positions(nav, venue)

        result: RebalanceResult = rebalance(
            pending,
            nav,
            self._book,
            instrument_metas=instrument_metas,
            fx_rates=fx_rates,
            prices=prices,
            held_positions=held_positions,
        )

        # ── Slice 9: compute total notional for the summary ──────────────
        total_notional = sum(
            abs(o.quantity) for o in result.orders
            if o.figi.value in self._period_fresh_figis
        )

        # ── Slice 9: build and log the rebalance summary ─────────────────
        summary = RebalanceSummary(
            nav=nav,
            num_sleeves=len(pending),
            num_targets=len(result.orders),
            num_orders=len(result.orders),
            num_quarantined=len(result.quarantined),
            quarantined_figis=result.quarantined,
            gate_outcome=GateOutcome.PASS,
            total_notional=total_notional,
        )
        self._log_rebalance_summary(summary)

        # Slice 7: alert on quarantined instruments
        if result.quarantined:
            self.log.warning(
                f"Quarantined instruments (held but not in any sleeve): "
                f"{', '.join(result.quarantined)}"
            )

        # ── Slice 9: store per-sleeve targets & closes for attribution ───
        for sleeve_name, target_df in pending.items():
            history = self._sleeve_target_history.setdefault(sleeve_name, [])
            history.append(target_df)
        if prices:
            for figi, px in prices.items():
                cl = self._close_history.setdefault(figi, [])
                cl.append(px)

        # Calendar-aware: only emit orders for FIGIs with a fresh bar
        for oi in result.orders:
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
                f"quarantined={summary.num_quarantined} "
                f"gate={summary.gate_outcome.value} "
                f"notional={summary.total_notional:.2f}"
            )

    def on_stop(self) -> None:
        """Compute and log per-sleeve P&L attribution at end of run.

        Attribution is computed from the history of sleeve targets and
        close prices collected during the run.  When insufficient data
        exists (fewer than 2 periods per FIGI), attribution is skipped.
        """
        if not self._sleeve_target_history or not self._close_history:
            return

        # Build consolidated sleeve targets — each target_list entry is a
        # single-row DataFrame; concat produces a multi-row frame indexed
        # by the original bar timestamps.
        sleeve_targets: dict[SleeveName, pd.DataFrame] = {}
        for sleeve_name, target_list in self._sleeve_target_history.items():
            if not target_list:
                continue
            all_targets = pd.concat(target_list)
            sleeve_targets[sleeve_name] = all_targets

        if not sleeve_targets:
            return

        # Build a closes DataFrame with the same index as the targets.
        # Use the union of all target timestamps as the index.
        all_idxs = [df.index for df in sleeve_targets.values()]
        combined_idx = all_idxs[0]
        for idx in all_idxs[1:]:
            combined_idx = combined_idx.union(idx)
        combined_idx = combined_idx.sort_values()
        combined_idx.name = "timestamp"

        if len(combined_idx) < 2:
            return

        closes_data: dict[str, list[float]] = {}
        for figi, px_list in self._close_history.items():
            if len(px_list) < 2:
                continue
            # Align to the combined index (pad with NaN at the front)
            padded = [float("nan")] * max(0, len(combined_idx) - len(px_list)) + px_list
            padded = padded[-len(combined_idx):]  # trim to index length
            closes_data[figi] = padded

        if not closes_data:
            return

        closes_df = pd.DataFrame(closes_data, index=combined_idx)
        closes_df.columns.name = "figi"

        nav_series = pd.Series([100_000.0] * len(combined_idx), index=combined_idx)

        attribution = compute_sleeve_attribution(
            sleeve_targets=sleeve_targets,
            closes=closes_df,
            nav_series=nav_series,
        )

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

        Uses the FIGI bimap (Slice 3) when available, falling back to the
        per-sleeve venue map (Slice 6) or the book's default_venue.
        """
        if figi in self._figi_bimap:
            return self._figi_bimap[figi]
        venue = self._figi_to_venue.get(figi, self._book.default_venue)
        return InstrumentId.from_str(f"{figi}.{venue}")

    def _resolve_bimap(self, figis: set[str]) -> dict[str, InstrumentId]:
        """Resolve *figis* to a bimap via the Security Master."""
        return self._figi_resolver.resolve(figis)

    def _collect_sizing_params(
        self, venue: Venue
    ) -> tuple[dict[str, InstrumentSizing], dict[str, float], dict[str, float]]:
        """Gather per-FIGI instrument metadata, FX rates, and latest close
        prices from Nautilus for sizing.

        Returns three dicts keyed by FIGI (instrument_metas/prices) or
        currency (fx_rates).  An instrument that cannot be resolved from the
        cache is silently omitted (the rebalancer will fall back to raw
        notional for it).
        """
        instrument_metas: dict[str, InstrumentSizing] = {}
        prices: dict[str, float] = {}
        currencies: set[str] = set()

        # Collect all FIGIs from all sleeves
        all_figis: set[str] = set()
        for bundle in self._sleeve_to_bundle.values():
            all_figis.update(bundle.contract.figis)

        for figi_str in all_figis:
            instr_id = self._figi_to_instr_id(figi_str)
            instrument = self.cache.instrument(instr_id)
            if instrument is None:
                continue

            currency = instrument.quote_currency.code
            instrument_metas[figi_str] = InstrumentSizing(
                currency=currency,
                size_increment=float(instrument.size_increment),
            )

            buf = self._bars_buffer.get(instr_id)
            if buf:
                prices[figi_str] = float(buf[-1].close.as_double())

            currencies.add(currency)

        fx_rates: dict[str, float] = {}
        for currency in currencies:
            rate = self._get_fx_rate(venue, currency)
            if rate is not None:
                fx_rates[currency] = rate

        return instrument_metas, fx_rates, prices

    def _collect_held_positions(
        self, nav: float, venue: Venue,
    ) -> dict[str, float]:
        """Collect broker positions for FIGIs NOT in any sleeve contract.

        Returns a dict of FIGI → signed weight (position value / NAV).
        Positions for FIGIs that are covered by at least one sleeve contract
        are excluded — they are tracked via ``realized_weights`` instead.

        An empty dict when no held positions exist or NAV ≤ 0.
        """
        if nav <= 0:
            return {}

        # Collect all FIGIs covered by any sleeve
        tracked_figis: set[str] = set()
        for contract in self._sleeve_to_contract.values():
            tracked_figis.update(contract.figis)

        held: dict[str, float] = {}
        positions = self.cache.positions()
        if not positions:
            return {}

        for pos in positions:
            if not pos.is_open:
                continue
            instr_id = pos.instrument_id
            # Resolve InstrumentId back to FIGI via the instr→figi map
            figi = self._instr_to_figi.get(instr_id.value)
            if figi is None:
                # Fallback: strip the venue suffix to recover the FIGI
                parts = instr_id.value.rsplit(".", 1)
                if len(parts) == 2 and parts[0]:
                    candidate = parts[0]
                    if candidate in tracked_figis:
                        continue  # tracked by some sleeve → not quarantined
                    figi = candidate
            elif figi in tracked_figis:
                continue  # tracked by some sleeve → not quarantined

            # Compute signed weight from net quantity
            instrument = self.cache.instrument(instr_id)
            if instrument is None:
                continue
            price = self.cache.price(instr_id)
            if price is None:
                continue

            notional = float(pos.net_qty.as_double()) * float(price.as_double())
            held[figi or instr_id.value] = notional / nav

        return held

    def _get_fx_rate(self, venue: Venue, target_currency: str) -> float | None:
        """Get the FX rate in units of *target_currency* per 1 EUR.

        Returns None when the rate is unavailable (rebalancer falls back to
        raw EUR notional).

        Currently returns 1.0 for base currency, None for foreign currencies
        (FX rate sourcing from Nautilus cache will be wired in a later slice
        when per-venue FX data is integrated into the backtest engine).
        """
        if target_currency == self._book.base_currency:
            return 1.0
        # TODO(j4a.4): query Nautilus cache for FX rates when multi-ccy data
        # is available.  For now, foreign-currency instruments fall back to
        # raw notional (the rebalancer will not size them).
        return None

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

        Computes per-instrument max notionals from the current NAV.
        """
        figis: list[str] = []
        for contract in self._sleeve_to_contract.values():
            figis.extend(contract.figis)
        return self._risk_guard.risk_engine_config_dict(
            nav=nav,
            figis=figis,
            default_venue=self._book.default_venue,
        )

    # -- order submission -------------------------------------------------------

    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit.

        Slice 5: the OrderIntent quantity is already a native share count
        (sized by the rebalancer), so it is passed directly to ``make_qty``.
        """
        instr_id = self._figi_to_instr_id(oi.figi.value)
        instrument = self.cache.instrument(instr_id)
        if instrument is None:
            self.log.error(
                f"Instrument not found for FIGI {oi.figi.value}; skipping order"
            )
            return

        nt_side = NtOrderSide.BUY if oi.side == OrderSide.BUY else NtOrderSide.SELL
        quantity = instrument.make_qty(oi.quantity)
        order = self.order_factory.market(
            instrument_id=instr_id,
            order_side=nt_side,
            quantity=quantity,
        )
        self.submit_order(order)


def _bars_to_close_series(
    bars: list[Bar], figi: str,
) -> pd.DataFrame:
    """Convert buffered bars into a single-column close-price DataFrame keyed by *figi*."""
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [float(b.close.as_double()) for b in bars]
    return pd.DataFrame({figi: values}, index=index)
