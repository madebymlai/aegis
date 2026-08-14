"""Live IBKR provider check — operator-run, against a real IB Gateway.

IBKR is a true-external dependency: these tests connect to a running gateway, so
they are skipped unless ``ibapi`` is installed *and* ``AEGIS_IBKR_GATEWAY_PORT``
is set to the gateway's port.  The adapter's own logic (param translation, asyncio
hiding) is covered without IBKR in ``tests/test_ibkr.py``; these pin the
real contracts a fake cannot model — that the client returns ``EXTERNAL`` daily
bars, that ``request_instruments`` round-trips the native identity, and that the
full lazy fill persists real bars + the definition and then reads back warm.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogWindowRequest,
    bars_to_ohlcv,
    open_catalog,
)
from aegis_data.custom_data import CustomDataWarmer
from aegis_data.distributions import recover_distributions_from_adjusted_last
from aegis_data.ibkr import (
    IbkrHistoricalProvider,
    historic_custom_data_client_factory,
    historic_data_client_factory,
    seed_instrument_definitions,
)
from aegis_data.research_bars import CatalogBarWarmer

pytest.importorskip("ibapi")

_GATEWAY_PORT = os.environ.get("AEGIS_IBKR_GATEWAY_PORT")
# The MIC-pinned venue IB resolves NASDAQ to under convert_exchange_to_mic_venue
# (r8b.9): request_bars keys returned bars by the deterministic MIC venue, so the
# Catalog id — request, fill, and warm read alike — is AAPL.XNAS, not AAPL.NASDAQ.
_AAPL = InstrumentId.from_str("AAPL.XNAS")
_EUR_USD = InstrumentId.from_str("EUR/USD.IDEALPRO")
_SPY = InstrumentId.from_str("SPY.ARCA")
_GLD = InstrumentId.from_str("GLD.ARCA")
_CRNX = InstrumentId.from_str("CRNX.XNAS")
_START = pd.Timestamp("2024-01-02", tz="UTC")
_END = pd.Timestamp("2024-02-01", tz="UTC")

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def _provider() -> IbkrHistoricalProvider:
    # DELAYED_FROZEN so the checks run without a real-time data subscription;
    # they validate the read path + identity + persistence, not live streaming.
    # The real connection is a process singleton, so every test shares one client
    # (a second IB client per process aborts on the global Rust logger).
    return IbkrHistoricalProvider(
        port=int(_GATEWAY_PORT),  # type: ignore[arg-type]
        client_id=7,
        market_data_type="DELAYED_FROZEN",
    )


def test_request_bars_returns_external_daily_bars_from_ibkr() -> None:
    served = _provider()._request_bars_for_engine(
        raw_bar_type(_AAPL, "1D"), start=_START, end=_END
    )

    assert served
    assert all(bar.bar_type == raw_bar_type(_AAPL, "1D") for bar in served)


def test_request_bars_returns_midpoint_daily_bars_for_cash_fx() -> None:
    """Cash FX has no TRADES print on IDEALPRO — a LAST request fails with IB error
    162 — so its raw bars are MID (``…-MID-EXTERNAL``, ADR-0007).  This pins that IB
    actually serves the MIDPOINT daily series the Catalog keys FX under; the bar type
    is derived through ``raw_bar_type`` exactly as the lazy fill builds it."""
    bar_type = raw_bar_type(_EUR_USD, "1D")
    assert bar_type.spec.price_type == PriceType.MID

    served = _provider()._request_bars_for_engine(bar_type, start=_START, end=_END)

    assert served
    assert all(bar.bar_type == bar_type for bar in served)


def test_request_instruments_round_trips_native_identity() -> None:
    """The IB-simplified symbology returns a definition whose id is the native
    InstrumentId we asked for — the invariant AC6's catalog lookup relies on."""
    instruments = _provider().request_instruments((_AAPL,))

    assert any(instrument.id == _AAPL for instrument in instruments)


def _upcoming_es_quarterly_legs(
    now: pd.Timestamp, count: int = 4
) -> list[InstrumentId]:
    """The next ``count`` ES quarterly leg ids (IB simplified symbology, MIC venue) after ``now``.

    ES rolls on the quarterly cycle H(Mar)/M(Jun)/U(Sep)/Z(Dec); the leg id is
    ``ES{code}{single-digit-year}.XCME``.  Generated from the date — starting two months out to
    skip a near-expiry front — so the check never rots as contracts roll."""
    code = {3: "H", 6: "M", 9: "U", 12: "Z"}
    legs: list[InstrumentId] = []
    cursor = (now + pd.DateOffset(months=2)).replace(day=1)
    while len(legs) < count:
        if cursor.month in code:
            legs.append(
                InstrumentId.from_str(f"ES{code[cursor.month]}{cursor.year % 10}.XCME")
            )
        cursor = cursor + pd.DateOffset(months=1)
    return legs


def test_request_instruments_loads_dated_futures_legs_mic_qualified() -> None:
    """A continuous book rolls into dated legs at runtime (Slice G — the live daemon has no
    preloaded horizon, so each new front is loaded via request_instrument).  The provider must
    qualify a leg's simplified-symbology id to a FuturesContract whose venue is MIC-pinned
    (IB exchange CME → XCME) with underlying ES — the identity the continuous-root id, the catalog
    lookup, and root→front execution all rely on."""
    legs = _upcoming_es_quarterly_legs(pd.Timestamp.now(tz="UTC"))

    by_id = {inst.id: inst for inst in _provider().request_instruments(legs)}

    assert len(by_id) >= 2  # the front and at least one roll-ahead leg load
    for leg_id, leg in by_id.items():
        assert isinstance(leg, FuturesContract)
        assert (
            leg_id.venue.value == "XCME"
        )  # CME exchange MIC-pinned (request used .XCME)
        assert str(leg.underlying) == "ES"


def test_lazy_fill_backfills_persists_and_then_reads_warm(tmp_path) -> None:
    """The production composition end to end against real IBKR: a miss fills bars
    AND seeds the definition; a provider-less re-read then serves from the catalog
    (warm, no IBKR), and the instrument definition is present (AC1/AC3/AC6)."""
    catalog_path = tmp_path / "catalog"
    provider = _provider()
    catalog = open_catalog(catalog_path)
    port = CatalogBackedDataPort(
        catalog,
        provider=CatalogBarWarmer(catalog, historic_data_client_factory(provider)),
        # The window read verifies distribution coverage too (ADR-0012), so the
        # fill port carries both provider roles — the production composition.
        custom_data_warmer=CustomDataWarmer(
            catalog,
            historic_custom_data_client_factory(provider),
        ),
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )
    request = CatalogWindowRequest(
        instrument_ids=(_AAPL,), start="2024-01-02", end="2024-02-01"
    )

    filled = port.load_window(request).ohlcv
    assert not filled[_AAPL].empty
    assert (filled[_AAPL]["Close"] > 0).all()

    # Provider-less read: must serve entirely from the catalog (no IBKR contact).
    warm = CatalogBackedDataPort(open_catalog(catalog_path)).load_window(request).ohlcv
    assert warm[_AAPL]["Close"].tolist() == filled[_AAPL]["Close"].tolist()

    # AC6: the served instrument's definition was persisted as a Step-1 write.
    definitions = open_catalog(catalog_path).definitions((_AAPL,))
    assert any(instrument.id == _AAPL for instrument in definitions)


def test_adjusted_last_decode_recovers_spy_dividends_and_gld_control() -> None:
    """Operator-run dividend source check: TRADES rides the standard bar path,
    ADJUSTED_LAST rides the persistent Nautilus session, and the ratio recovers
    real gross distributions while the GLD non-distributor stays empty."""
    provider = _provider()
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2026-06-01", tz="UTC")

    spy_trades = bars_to_ohlcv(
        provider._request_bars_for_engine(
            raw_bar_type(_SPY, "1D"), start=start, end=end
        )
    )["Close"]
    gld_trades = bars_to_ohlcv(
        provider._request_bars_for_engine(
            raw_bar_type(_GLD, "1D"), start=start, end=end
        )
    )["Close"]
    spy = tuple(
        recover_distributions_from_adjusted_last(
            instrument_id=_SPY,
            trades=spy_trades,
            adjusted_last=provider.request_adjusted_last(
                _SPY, start=start, end=end, currency="USD"
            ),
            currency="USD",
        )
    )
    gld = tuple(
        recover_distributions_from_adjusted_last(
            instrument_id=_GLD,
            trades=gld_trades,
            adjusted_last=provider.request_adjusted_last(
                _GLD, start=start, end=end, currency="USD"
            ),
            currency="USD",
        )
    )

    assert len(spy) >= 6
    assert sum(event.amount for event in spy) > 10.0
    assert gld == ()


def test_adjusted_last_returns_closes_through_the_persistent_session() -> None:
    provider = _provider()
    start = pd.Timestamp("2026-06-01", tz="UTC")
    end = pd.Timestamp("2026-07-16", tz="UTC")

    adjusted = provider.request_adjusted_last(
        _CRNX,
        start=start,
        end=end,
        currency="USD",
    )

    assert not adjusted.empty
    assert adjusted.index.min() >= start
    assert adjusted.index.max() <= end
    assert (adjusted > 0).all()
