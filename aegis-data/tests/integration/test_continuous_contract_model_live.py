"""Live-gateway checks for ContinuousContractModel on real IB data."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import timedelta

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest, parquet_data_catalog
from aegis_data.catalog_contracts import catalog_contract_calendar
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.ibkr import IbkrHistoricalProvider, seed_instrument_definitions
from aegis_data.roll import front_contract as calendar_front
from aegis_data.roll import roll_lead_days_for_cadence

_GATEWAY_PORT = os.environ.get("AEGIS_IBKR_GATEWAY_PORT")
_ESM6 = InstrumentId.from_str("ESM6.XCME")
_ESU6 = InstrumentId.from_str("ESU6.XCME")
_ES = InstrumentId.from_str("ES.XCME")
_START, _END = "2026-03-02", "2026-06-23"

_PAM6 = InstrumentId.from_str("PAM6.XNYM")
_PAU6 = InstrumentId.from_str("PAU6.XNYM")
_PA_START, _PA_END, _PA_FILL_END = "2026-03-02", "2026-06-10", "2026-06-23"
_DAILY_ROLL_LEAD = roll_lead_days_for_cadence(timedelta(days=1))

pytestmark = pytest.mark.skipif(
    _GATEWAY_PORT is None,
    reason="set AEGIS_IBKR_GATEWAY_PORT to run against a live IB Gateway",
)


def _warm_catalog(
    tmp_path, legs: Sequence[InstrumentId], start: str, end: str
) -> CatalogBackedDataPort:
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


def test_model_front_authority_matches_the_series_front_on_a_real_roll(tmp_path) -> None:
    warm = _warm_catalog(tmp_path, (_ESM6, _ESU6), _START, _END)
    model = ContinuousContractModel(warm, "ES", start=_START, timeframe="1D")
    model.materialize(end=_END)

    assert model.front_leg == _ESU6
    last = model.frame.index[-1]
    front_close = next(
        float(bar.close.as_double())
        for bar in _front_leg_bars(warm, model.front_leg, _START, _END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )
    assert model.frame.loc[last, "Close"] == pytest.approx(front_close)


def test_model_offset_zero_append_recovers_research_on_real_data(tmp_path) -> None:
    warm = _warm_catalog(tmp_path, (_ESM6, _ESU6), _START, _END)
    oracle_model = ContinuousContractModel(warm, "ES", start=_START, timeframe="1D")
    oracle_model.materialize(end=_END)
    oracle = oracle_model.frame
    assert oracle_model.continuous_id == _ES
    last = oracle.index[-1]
    append_bar = next(
        bar
        for bar in _front_leg_bars(warm, _ESU6, _START, _END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )

    model = ContinuousContractModel(warm, "ES", start=_START, timeframe="1D")
    model.materialize(end="2026-06-19")
    pd.testing.assert_frame_equal(model.frame, oracle.iloc[:-1])

    model.on_bar(append_bar)

    pd.testing.assert_frame_equal(model.frame, oracle)


def test_thin_root_extends_the_model_onto_the_early_liquidity_leader(tmp_path) -> None:
    warm = _warm_catalog(tmp_path, (_PAM6, _PAU6), _PA_START, _PA_FILL_END)
    model = ContinuousContractModel(warm, "PA", start=_PA_START, timeframe="1D")
    model.materialize(end=_PA_END)

    legs = catalog_contract_calendar(warm.catalog)(
        "PA", pd.Timestamp(_PA_START).date(), pd.Timestamp(_PA_END).date()
    )
    calendar_leg = calendar_front(legs, pd.Timestamp(_PA_END).date(), roll_lead_days=_DAILY_ROLL_LEAD)
    assert calendar_leg is not None and calendar_leg.symbol == _PAM6.value

    assert model.front_leg == _PAU6
    last = model.frame.index[-1]
    front_close = next(
        float(bar.close.as_double())
        for bar in _front_leg_bars(warm, model.front_leg, _PA_START, _PA_FILL_END)
        if pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None) == last
    )
    assert model.frame.loc[last, "Close"] == pytest.approx(front_close)
