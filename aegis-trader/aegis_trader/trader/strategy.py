"""RebalanceStrategy — the NautilusTrader Strategy that drives the
commingling overlay.

Thin adapter: delegates alpha-to-orders to the pure-domain pipeline so the
core remains broker-free-testable.  Supports multi-sleeve netting: each
sleeve's bundle computes its target weights, which the rebalancer nets
across sleeves before submitting orders.

NEXT-CLOSE execution (ADR-0001): the target decided at bar t's close is
submitted on bar t+1 and fills at bar t+1's close — one-bar lag, no look-ahead.

RiskEngine guards (Slice 8): the ``RiskGuard`` computes per-instrument
max-notional caps from NAV; the strategy logs every ``OrderDenied`` event
so operators can trace rejected orders.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide as NtOrderSide
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from aegis_runtime import DataContract, ExecutionBundle, MarketDataBundle

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.rebalancer import rebalance
from aegis_trader.domain.risk_guard import RiskGuard, RiskGuardConfig
from aegis_trader.domain.types import OrderIntent, OrderSide, SleeveName


class RebalanceStrategyConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]  # msgspec metaclass not in stubs
    """Configuration for the RebalanceStrategy."""

    book: BookConfig
    bundle_label: str = "synthetic"
    risk_guard_config: RiskGuardConfig = RiskGuardConfig()


class RebalanceStrategy(Strategy):
    """Commingled-book rebalance overlay — submits orders NEXT-CLOSE.

    Buffer bars as they arrive; when enough lookback is accumulated, assemble
    a MarketDataBundle each bar, call the bundle's compute_weights, and store
    the latest row as the next-bar target.  On the *following* bar, submit
    order(s) from the previously-stored targets — implementing the one-bar
    execution lag.

    In single-sleeve mode (Slice 1) the base class handles everything.
    Multi-sleeve setups (Slice 2+) extend this class and accumulate
    per-sleeve targets into ``_pending_targets`` before calling
    ``_submit_pending_orders()``.
    """

    def __init__(self, config: RebalanceStrategyConfig) -> None:
        super().__init__(config)
        self._book: BookConfig = config.book
        self._bundle: ExecutionBundle | None = None
        self._contract: DataContract | None = None
        self._bars_buffer: dict[InstrumentId, list[Bar]] = {}
        self._pending_targets: dict[SleeveName, pd.DataFrame] = {}
        self._risk_guard: RiskGuard = RiskGuard(config.risk_guard_config)

    def on_start(self) -> None:
        sleeve = self._book.sleeves[0]
        if self._bundle is None:
            self.log.warning("No bundle injected; strategy will idle.")
            return
        self._contract = self._bundle.contract
        figis = self._contract.figis
        # For Slice 1 we resolve FIGI→InstrumentId by convention (FIGI.VENUE).
        # The Security Master (Slice 3) replaces this.
        for figi in figis:
            bar_type = BarType.from_str(f"{self._figi_to_instr_id(figi).value}-1-DAY-LAST-EXTERNAL")
            self.subscribe_bars(bar_type)
        self.log.info(f"RebalanceStrategy starting; sleeve={sleeve.name.value}, figis={figis}")

    def on_bar(self, bar: Bar) -> None:
        if self._bundle is None or self._contract is None:
            return

        buf = self._buffer_bar(bar)
        if buf is None:
            return  # not enough lookback bars yet

        target = self._compute_target(buf)
        self._submit_pending_orders()
        sleeve_name = self._book.sleeves[0].name
        self._pending_targets[sleeve_name] = target

    def _buffer_bar(self, bar: Bar) -> list[Bar] | None:
        """Buffer *bar* into its per-instrument window and return the window
        if enough lookback bars have accumulated, otherwise None."""
        if self._contract is None:  # pragma: no cover — guard, on_bar already checks
            return None
        instr_id = bar.bar_type.instrument_id
        buf = self._bars_buffer.setdefault(instr_id, [])
        buf.append(bar)

        lookback = self._contract.lookback_bars
        needed = lookback + 1  # lookback bars + the current bar
        if len(buf) < needed:
            return None

        # Drop excess beyond what we need
        if len(buf) > needed:
            buf[:] = buf[-needed:]
        return buf

    def _compute_target(self, buf: list[Bar]) -> pd.DataFrame:
        """Assemble a MarketDataBundle from *buf* and call compute_weights."""
        assert self._contract is not None  # guarded by on_bar
        assert self._bundle is not None  # guarded by on_bar
        # For Slice 1 the buffer is per-instrument with a 1:1 FIGI mapping.
        close_series = _bars_to_close_series(buf, self._contract.figis[0])
        bundle_data = MarketDataBundle({"Close": close_series})
        # For Slice 1 we pass no FX series (single-currency EUR)
        return self._bundle.compute_weights(bundle_data)

    def _submit_pending_orders(self) -> None:
        """Submit orders for the target computed on the previous bar.

        This is the one-bar lag: the target was decided at bar t-1 and is now
        submitted on bar t, filling at bar t's close.
        """
        if not self._pending_targets:
            return
        venue = Venue(self._book.default_venue)
        equity_map = self.portfolio.equity(venue=venue)
        base_ccy = Currency.from_str(self._book.base_currency)
        nav = float(equity_map[base_ccy].as_double())
        orders = rebalance(self._pending_targets, nav, self._book)
        self._pending_targets = {}
        for oi in orders:
            self._submit_order_intent(oi)

    def _figi_to_instr_id(self, figi: str) -> InstrumentId:
        """Resolve a FIGI to a venue-specific InstrumentId.

        For Slice 1 resolved by convention (FIGI.VENUE).
        The Security Master (Slice 3) replaces this.
        """
        return InstrumentId.from_str(f"{figi}.{self._book.default_venue}")

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
        if self._contract is not None:
            figis = list(self._contract.figis)
        return self._risk_guard.risk_engine_config_dict(
            nav=nav,
            figis=figis,
            default_venue=self._book.default_venue,
        )

    # -- order submission -------------------------------------------------------

    def _submit_order_intent(self, oi: OrderIntent) -> None:
        """Translate a domain OrderIntent into a Nautilus MARKET order and submit."""
        instr_id = self._figi_to_instr_id(oi.figi.value)
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
    bars: list[Bar], figi: str
) -> pd.DataFrame:
    """Convert buffered bars into a single-column close-price DataFrame keyed by *figi*."""
    index = pd.DatetimeIndex([b.ts_event for b in bars])
    values = [float(b.close.as_double()) for b in bars]
    return pd.DataFrame({figi: values}, index=index)
