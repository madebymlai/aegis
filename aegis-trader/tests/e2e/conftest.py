"""e2e test isolation.

NautilusTrader's ``BacktestEngine`` initialises process-global state (the
logger and the Rust runtime) that aborts the interpreter when a second engine
is constructed in the same process — hence the "one BacktestEngine per process"
note in each e2e module.  Running each e2e test in its own forked subprocess
(via ``pytest-forked``) makes the suite deterministic without constraining how
many engines a single test builds.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nautilus_trader.model.currencies import EUR, GBP
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity, FuturesContract
from nautilus_trader.model.objects import Price, Quantity

_E2E_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # pytest invokes this hook once per session with *every* collected item, not
    # just the ones under tests/e2e — so scope the forked marker to e2e items.
    # Otherwise the unit tests fork too: needlessly (they share no engine state)
    # and noisily (each fork emits the fork()-in-a-multi-threaded-process warning).
    for item in items:
        if item.path.is_relative_to(_E2E_DIR):
            item.add_marker(pytest.mark.forked)


def eur_equity(symbol: str, venue: str) -> Equity:
    """A EUR-denominated equity for e2e tests.

    The overlay's base currency is EUR, so EUR instruments size at FX=1.0 — that
    keeps the e2e focused on the overlay (netting, cadence, timing, risk) without
    needing cross-currency FX data (which is Wave C).  ``TestInstrumentProvider.
    equity`` is USD-only, so we build our own.
    """
    return Equity(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue(venue)),
        raw_symbol=Symbol(symbol),
        currency=EUR,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def eur_future(symbol: str, venue: str) -> FuturesContract:
    """A EUR-denominated, ×1-multiplier dated futures contract for e2e tests.

    Mirrors ``eur_equity`` (EUR ⇒ FX=1.0, multiplier/lot 1 ⇒ sizing is
    share-like) so the futures-roll e2e exercises the *identity + roll* path
    without dragging in contract-multiplier or cross-currency concerns.  The
    active window is opened wide (epoch → 2100) so the synthetic epoch-anchored
    bars fall inside it.  ``TestInstrumentProvider.future`` is USD-only, so we
    build our own.
    """
    return FuturesContract(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue(venue)),
        raw_symbol=Symbol(symbol),
        asset_class=AssetClass.INDEX,
        exchange=venue,
        currency=EUR,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        multiplier=Quantity.from_int(1),
        lot_size=Quantity.from_int(1),
        underlying=symbol[:2],
        activation_ns=0,
        expiration_ns=4_102_444_800_000_000_000,  # 2100-01-01
        ts_event=0,
        ts_init=0,
    )


def gbp_equity(symbol: str, venue: str) -> Equity:
    """A GBP-denominated equity for the Wave C cross-currency e2e (sizes against
    an EUR book via a GBP/EUR FX rate)."""
    return Equity(
        instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue(venue)),
        raw_symbol=Symbol(symbol),
        currency=GBP,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
