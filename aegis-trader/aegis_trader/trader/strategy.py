"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

Slice 6 — cadence (per-sleeve timeframe + calendar-aware):
- Each sleeve rebalances off bar-close at its own DataContract.timeframe.
- Debounced: one re-net per completed period, not per-instrument-bar churn.
- Calendar-aware: orders emitted only for instruments whose venue is open
  (had a fresh bar during the completed period).
- Drift is evaluated every period even on an unchanged target.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_runtime import DataContract, ExecutionBundle, MarketDataBundle

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.types import OrderIntent, OrderSide, SleeveName

_NS_PER_DAY: int = 86_400_000_000_000


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"


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

        # Build FIGI → venue map from sleeve configs
        for sleeve in self._book.sleeves:
            venue = sleeve.venue or self._book.default_venue
            bundle = self._sleeve_to_bundle.get(sleeve.name)
            if bundle is None:
                continue
            for figi in bundle.contract.figis:
                self._figi_to_venue[figi] = venue

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
        if not self._sleeve_to_bundle:
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
        """
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
        orders = rebalance(pending, nav, self._book)

        # Calendar-aware: only emit orders for FIGIs with a fresh bar
        for oi in orders:
            if oi.figi.value not in self._period_fresh_figis:
                self.log.info(
                    f"Skipping {oi.side.value} {oi.quantity:.0f} "
                    f"{oi.figi.value}: venue closed this period"
                )
                continue
            self._submit_order_intent(oi)

    def _figi_to_instr_id(self, figi: str) -> InstrumentId:
        """Resolve a FIGI to a venue-specific InstrumentId.

        Uses the per-sleeve venue map when available (Slice 6), falling
        back to the book's default_venue (Slice 1 backward compat).
        The Security Master (Slice 3) replaces the FIGI.VENUE convention.
        """
        venue = self._figi_to_venue.get(figi, self._book.default_venue)
        return InstrumentId.from_str(f"{figi}.{venue}")

    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit."""
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
