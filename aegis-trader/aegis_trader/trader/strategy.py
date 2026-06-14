"""RebalanceStrategy — the single NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  For Slice 1 (tracer) this handles a single
sleeve with no bands, gates, or position diffing.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.
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
from aegis_trader.domain.types import OrderIntent, OrderSide


class RebalanceStrategyConfig(StrategyConfig, frozen=True):
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"


class RebalanceStrategy(Strategy):
    """Single-sleeve rebalance overlay — submits orders NEXT-CLOSE.

    Buffer bars as they arrive; when enough lookback is accumulated, assemble
    a MarketDataBundle each bar, call the bundle's compute_weights, and store
    the latest row as the next-bar target.  On the *following* bar, submit
    order(s) from the previously-stored target — implementing the one-bar
    execution lag.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._book: BookConfig = config.book
        self._bundle: ExecutionBundle | None = None
        self._contract: DataContract | None = None
        self._bars_buffer: dict[InstrumentId, list[Bar]] = {}
        self._pending_target: pd.DataFrame | None = None
        self._bar_type: BarType | None = None

    def on_start(self) -> None:
        sleeve = self._book.sleeves[0]
        if self._bundle is None:
            self.log.warning("No bundle injected; strategy will idle.")
            return
        self._contract = self._bundle.contract
        figis = self._contract.figis
        # For Slice 1 we resolve FIGI→InstrumentId by convention (FIGI.VENUE).
        # The Security Master (Slice 3) replaces this.
        venue = self._book.default_venue
        for figi in figis:
            instr_id = InstrumentId.from_str(f"{figi}.{venue}")
            bar_type = BarType.from_str(f"{instr_id.value}-1-DAY-LAST-EXTERNAL")
            self.subscribe_bars(bar_type)
        self.log.info(f"RebalanceStrategy starting; sleeve={sleeve.name.value}, figis={figis}")

    def on_bar(self, bar: Bar) -> None:
        if self._bundle is None or self._contract is None:
            return

        # Buffer the bar
        instr_id = bar.bar_type.instrument_id
        buf = self._bars_buffer.setdefault(instr_id, [])
        buf.append(bar)

        lookback = self._contract.lookback_bars
        total = len(buf)
        needed = lookback + 1  # lookback bars + the current bar
        if total < needed:
            return

        # Drop excess beyond what we need
        if total > needed:
            buf[:] = buf[-needed:]

        # Assemble MarketDataBundle
        close_series = _bars_to_close_series(buf, self._contract.figis)
        bundle_data = MarketDataBundle({"Close": close_series})
        # For Slice 1 we pass no FX series (single-currency EUR)
        target = self._bundle.compute_weights(bundle_data)

        # If we have a pending target from a previous bar, submit now.
        # This is the one-bar lag: the target was computed at bar t-1 and
        # is now being submitted on bar t, filling at bar t's close.
        if self._pending_target is not None:
            venue = Venue(self._book.default_venue)
            equity_map = self.portfolio.equity(venue=venue)
            base_ccy = Currency.from_str(self._book.base_currency)
            nav = float(equity_map[base_ccy].as_double())
            orders = rebalance(self._pending_target, nav, self._book)
            for oi in orders:
                self._submit_order_intent(oi)

        # Store current target for next bar
        self._pending_target = target


    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit.

        For Slice 1 we resolve FIGI→InstrumentId by convention (FIGI.VENUE).
        The real Security Master (Slice 3) replaces this.
        """
        venue = self._book.default_venue
        instr_id = InstrumentId.from_str(f"{oi.figi.value}.{venue}")
        instrument = self.cache.instrument(instr_id)
        if instrument is None:
            self.log.error(f"Instrument not found for FIGI {oi.figi.value}; skipping order")
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
    bars: list[Bar], figis: tuple[str, ...]
) -> pd.DataFrame:
    """Convert buffered bars into a close-price DataFrame keyed by FIGI.

    For Slice 1 the buffer is per-instrument and we assume one FIGI per
    instrument; the mapping is 1:1.
    """
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [float(b.close.as_double()) for b in bars]
    return pd.DataFrame(
        {figis[0]: values},
        index=index,
    )
