"""Live-gateway checks for the continuous feed on REAL IB data (r8b.9 .5, gateway-data subset).

IBKR is a true-external dependency: these connect to a running gateway, so they are skipped unless
``ibapi`` is installed *and* ``AEGIS_IBKR_GATEWAY_PORT`` is set (the convention from aegis-data's
``test_ibkr_provider_live``).  They pin two invariants a synthetic fixture cannot model on real
expiry-driven contracts:

1. **front-authority parity** — the feed's causal front (``liquid_cycle_causal``) is the leg the
   materialized series is anchored on at offset 0 (``fetch_contract_chain``); the two roll
   authorities agree on a real roll (the Slice D caveat, memory ``r8b9-feed-roll-authority``).
2. **offset-0 append == research** — appending today's real front bar (``ts_event`` = session open
   00:00 UTC, ``ts_init`` = session close) recovers research's still-forming last row byte-for-byte
   — the regression for the ``ts_init`` stamping bug this gateway work surfaced.

The fixture is the real ES M6→U6 roll (ESM6 expired 2026-06-19, ESU6 the active front), over a
fixed past window so the historical data is stable.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest, parquet_data_catalog
from aegis_data.continuous_catalog import continuous_ohlcv_frames
from aegis_data.ibkr import IbkrHistoricalProvider, seed_instrument_definitions
from aegis_trader.data.continuous_feed import ContinuousFeed

# NOTE: no module-level ``importorskip('ibapi')`` here (unlike aegis-data's gateway tests): ibapi
# IS installed in this venv, so importing it at collection would trip the lazy-import guard
# (test_cost_models_do_not_import_ibapi).  The env-var skipif is the gate; ibapi is imported lazily
# by the provider only inside a test, when actually connecting.
_GATEWAY_PORT = os.environ.get("AEGIS_IBKR_GATEWAY_PORT")
_ESM6 = InstrumentId.from_str("ESM6.XCME")  # Jun 2026, expired 2026-06-19
_ESU6 = InstrumentId.from_str("ESU6.XCME")  # Sep 2026, the front after the M6→U6 roll
_ES = InstrumentId.from_str("ES.XCME")
_START, _END = "2026-03-02", "2026-06-23"

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def _warm_catalog(tmp_path) -> CatalogBackedDataPort:
    """Fill the real ES M6/U6 leg bars + definitions into a temp catalog, return a warm
    (provider-less) read port over it."""
    provider = IbkrHistoricalProvider(
        port=int(_GATEWAY_PORT),  # type: ignore[arg-type]
        client_id=7,
        market_data_type="DELAYED_FROZEN",
    )
    path = tmp_path / "catalog"
    catalog = parquet_data_catalog(path)
    fill_port = CatalogBackedDataPort(
        catalog,
        provider=provider,
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )
    fill_port.load_raw_bars(
        RawBarRequest(instrument_ids=(_ESM6, _ESU6), start=_START, end=_END)
    )
    return CatalogBackedDataPort(parquet_data_catalog(path))


def _front_leg_bars(warm: CatalogBackedDataPort, leg: InstrumentId) -> list:
    return warm.read_native_bars(
        RawBarRequest(instrument_ids=(leg,), start=_START, end=_END, timeframe="1D")
    )[leg]


def test_feed_front_authority_matches_the_series_front_on_a_real_roll(tmp_path) -> None:
    warm = _warm_catalog(tmp_path)
    feed = ContinuousFeed(warm, "ES", start=_START, timeframe="1D")
    feed.materialize(end=_END)

    # The causal front rolled to the new leg on real volume.
    front = feed.front_contract()
    assert front == _ESU6

    # front-authority parity: the series' offset-0 value IS the front leg's raw close (verbatim) at
    # the same bucket close — so front_contract() is exactly the leg the series is anchored on.
    series = feed.series()
    last = series.index[-1]
    front_close = next(
        float(bar.close.as_double())
        for bar in _front_leg_bars(warm, front)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )
    assert series.loc[last, "Close"] == pytest.approx(front_close)


def test_offset_zero_append_recovers_research_on_real_data(tmp_path) -> None:
    warm = _warm_catalog(tmp_path)
    oracle = continuous_ohlcv_frames(warm, ["ES"], start=_START, end=_END)[_ES]
    last = oracle.index[-1]
    # The real front bar whose bucket close is research's still-forming last row (ts_init-stamped).
    append_bar = next(
        bar
        for bar in _front_leg_bars(warm, _ESU6)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )

    feed = ContinuousFeed(warm, "ES", start=_START, timeframe="1D")
    feed.materialize(end="2026-06-19")  # research minus the final still-forming bucket
    pd.testing.assert_frame_equal(feed.series(), oracle.iloc[:-1])

    feed.on_bar(append_bar)  # today's real front bar, appended at offset 0

    pd.testing.assert_frame_equal(feed.series(), oracle)  # live ≡ research, byte-for-byte
