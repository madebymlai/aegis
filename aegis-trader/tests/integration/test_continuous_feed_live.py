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
from collections.abc import Sequence
from datetime import timedelta

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest, parquet_data_catalog
from aegis_data.catalog_contracts import catalog_contract_calendar
from aegis_data.continuous_catalog import continuous_ohlcv_frames
from aegis_data.ibkr import IbkrHistoricalProvider, seed_instrument_definitions
from aegis_data.roll import front_contract as calendar_front
from aegis_data.roll import roll_lead_days_for_cadence
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

# Palladium — a thin metal whose liquidity migrates weeks before expiry: PAU6 takes the smoothed
# volume lead on 2026-05-28, ~3 weeks before PAM6's calendar roll (last trade 2026-06-26 → roll
# 2026-06-19).  Materialized at _PA_END, which sits inside that window, the calendar front is still
# PAM6 but the liquid front is PAU6 — the early-crossover case ES (crossovers near expiry) cannot show.
_PAM6 = InstrumentId.from_str("PAM6.XNYM")
_PAU6 = InstrumentId.from_str("PAU6.XNYM")
# Fill past _PA_END so the materialize's read (which probes one bucket past end) stays covered.
_PA_START, _PA_END, _PA_FILL_END = "2026-03-02", "2026-06-10", "2026-06-23"
_DAILY_ROLL_LEAD = roll_lead_days_for_cadence(timedelta(days=1))

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def _warm_catalog(
    tmp_path, legs: Sequence[InstrumentId], start: str, end: str
) -> CatalogBackedDataPort:
    """Fill the given real leg bars + definitions into a temp catalog over ``[start, end]``, return a
    warm (provider-less) read port over it."""
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
    fill_port.load_raw_bars(RawBarRequest(instrument_ids=tuple(legs), start=start, end=end))
    return CatalogBackedDataPort(parquet_data_catalog(path))


def _front_leg_bars(
    warm: CatalogBackedDataPort, leg: InstrumentId, start: str, end: str
) -> list:
    return warm.read_native_bars(
        RawBarRequest(instrument_ids=(leg,), start=start, end=end, timeframe="1D")
    )[leg]


def test_feed_front_authority_matches_the_series_front_on_a_real_roll(tmp_path) -> None:
    warm = _warm_catalog(tmp_path, (_ESM6, _ESU6), _START, _END)
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
        for bar in _front_leg_bars(warm, front, _START, _END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )
    assert series.loc[last, "Close"] == pytest.approx(front_close)


def test_offset_zero_append_recovers_research_on_real_data(tmp_path) -> None:
    warm = _warm_catalog(tmp_path, (_ESM6, _ESU6), _START, _END)
    oracle = continuous_ohlcv_frames(warm, ["ES"], start=_START, end=_END)[_ES]
    last = oracle.index[-1]
    # The real front bar whose bucket close is research's still-forming last row (ts_init-stamped).
    append_bar = next(
        bar
        for bar in _front_leg_bars(warm, _ESU6, _START, _END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )

    feed = ContinuousFeed(warm, "ES", start=_START, timeframe="1D")
    feed.materialize(end="2026-06-19")  # research minus the final still-forming bucket
    pd.testing.assert_frame_equal(feed.series(), oracle.iloc[:-1])

    feed.on_bar(append_bar)  # today's real front bar, appended at offset 0

    pd.testing.assert_frame_equal(feed.series(), oracle)  # live ≡ research, byte-for-byte


def test_thin_root_extends_the_series_onto_the_early_liquidity_leader(tmp_path) -> None:
    """The window-edge EXTENSION on real data (bd aegis-rd-6qp).  Palladium's liquidity migrates to
    PAU6 ~3 weeks before PAM6's calendar roll, so at ``_PA_END`` (inside that window) the calendar
    front is still PAM6 — yet the feed must roll the series onto the liquidity leader PAU6, with
    ``front_contract`` naming it too, so execution and signal both track the liquid leg, not the
    thinning one.  ES only exercises the no-extension passthrough (its crossovers sit near expiry);
    this is the thin-root case the synthetic ``test_continuous_feed`` fixture models, here on real
    IB volume."""
    warm = _warm_catalog(tmp_path, (_PAM6, _PAU6), _PA_START, _PA_FILL_END)
    feed = ContinuousFeed(warm, "PA", start=_PA_START, timeframe="1D")
    feed.materialize(end=_PA_END)

    # By the calendar PAM6 is still front at _PA_END (its roll is 2026-06-19), so the series being on
    # PAU6 is the liquidity-leader extension at work, not the calendar passthrough the ES test covers.
    legs = catalog_contract_calendar(warm.catalog)(
        "PA", pd.Timestamp(_PA_START).date(), pd.Timestamp(_PA_END).date()
    )
    calendar_leg = calendar_front(legs, pd.Timestamp(_PA_END).date(), roll_lead_days=_DAILY_ROLL_LEAD)
    assert calendar_leg is not None and calendar_leg.symbol == _PAM6.value

    # Execution (front_contract) and signal (series offset-0) both track the liquidity leader PAU6.
    front = feed.front_contract()
    assert front == _PAU6
    series = feed.series()
    last = series.index[-1]
    front_close = next(
        float(bar.close.as_double())
        for bar in _front_leg_bars(warm, front, _PA_START, _PA_FILL_END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )
    assert series.loc[last, "Close"] == pytest.approx(front_close)
