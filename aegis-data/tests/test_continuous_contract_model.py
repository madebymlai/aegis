"""ContinuousContractModel interface tests."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from nautilus_trader.cache.cache import Cache
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import continuous_bar_type, raw_bar_type
from aegis_data.catalog import (
    CatalogBackedDataPort,
    ContinuousRootLegsNotFoundError,
    ContinuousRootVenueMismatchError,
)
from aegis_data.chain import fetch_contract_chain
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE, continuous_future
from aegis_data.liquidity import liquid_cycle_causal
from tests.support.continuous_oracle import backward_series
from aegis_data.testing import (
    ES_END,
    ES_START,
    FakeCatalog,
    bars,
    early_crossover_es_port,
    es_port,
    es_port_two_rolls,
    future,
    lead_frame,
)

_ES_XCME = InstrumentId.from_str("ES.XCME")
_ESH4 = InstrumentId.from_str("ESH4.XCME")
_ESM4 = InstrumentId.from_str("ESM4.XCME")
_ESU4 = InstrumentId.from_str("ESU4.XCME")
_RAW_SCALE = 10**16


def _bar_on(
    native: dict[InstrumentId, list[Bar]], instrument_id: InstrumentId, day: date
) -> Bar:
    return next(
        bar
        for bar in native[instrument_id]
        if pd.Timestamp(bar.ts_event, tz="UTC").date() == day
    )


def _expected_ohlcv_row(
    stamp: str, *, open_: float, high: float, low: float, close: float, volume: float
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [open_],
            "High": [high],
            "Low": [low],
            "Close": [close],
            "Volume": [volume],
        },
        index=pd.DatetimeIndex([stamp]),
    )


def _causal_front(port: CatalogBackedDataPort, root: str, as_of: date) -> InstrumentId:
    candidates = port.resolve_continuous(root).legs
    volume_by_symbol = {
        leg.symbol: port.probe_contract_volume(
            leg.symbol, pd.Timestamp(ES_START).date(), as_of
        )
        for leg in candidates
    }
    cycle = liquid_cycle_causal(candidates, volume_by_symbol, as_of, roll_lead_days=5)
    return InstrumentId.from_str(cycle[-1].symbol)


def test_continuous_contract_model_matches_the_oracle_keyed_by_root_id() -> None:
    port, native = es_port()

    chain = fetch_contract_chain(
        "ES",
        date(2024, 1, 15),
        date(2024, 5, 31),
        list_contracts=lambda *_args: port.resolve_continuous("ES").legs,
        fetch=port.fetch_contract_ohlcv,
        bar_cadence=timedelta(days=1),
        probe_volume=port.probe_contract_volume,
    )
    future = continuous_future(chain, InstrumentId.from_str("ES.XCME"))
    oracle = backward_series(native, future.transitions, mode=DEFAULT_ADJUSTMENT_MODE)

    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    model.materialize(end=ES_END)

    assert model.continuous_id == InstrumentId.from_str("ES.XCME")
    frame = model.frame
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame.index.is_monotonic_increasing and not frame.index.has_duplicates

    head = oracle[: len(frame)]
    assert frame["Close"].tolist() == pytest.approx(
        [bar.close_raw / _RAW_SCALE for bar in head]
    )
    assert frame["Open"].tolist() == pytest.approx(
        [bar.open_raw / _RAW_SCALE for bar in head]
    )
    assert frame["Open"].iloc[0] != pytest.approx(99.5)


def _materialized_two_roll_model() -> ContinuousContractModel:
    port, native = es_port_two_rolls()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    model.materialize(end="2024-06-10")
    model.on_bar(_bar_on(native, _ESU4, date(2024, 6, 14)))
    return model


def _replayed_across_the_roll(
    tie_order: tuple[InstrumentId, ...],
) -> tuple[ContinuousContractModel, pd.DataFrame]:
    """Warm a model pre-roll, then fold both legs' bars through ``on_bar`` across
    the ESH4->ESM4 roll, mirroring the live incremental-replay seam. ``tie_order``
    decides which leg's bar arrives first on a shared day — either leg's bar can
    be the roll trigger in a live stream."""
    port, native = es_port()
    oracle = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    oracle.materialize(end="2024-04-30")
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    model.materialize(end="2024-02-15")
    lower = pd.Timestamp("2024-02-15")
    bars = sorted(
        (bar for leg in tie_order for bar in native[leg]),
        key=lambda bar: bar.ts_event,
    )
    for bar in bars:
        bucket = pd.Timestamp(bar.ts_init, tz="UTC").ceil("1D").tz_localize(None)
        if not lower < bucket <= oracle.frame.index[-1]:
            continue
        index = model.frame.index
        if len(index) and bucket <= index[-1]:
            continue
        model.on_bar(bar)
    return model, oracle.frame


def _live_cache_with_raw_bar() -> Cache:
    live_cache = Cache()
    live_cache.add_instrument(future("ESH4.XCME", "2024-03-15"))
    leg_bar = bars(
        _ESH4, lead_frame(ES_START, "2024-01-20", 100.0, ES_START, "2024-01-20")
    )[0]
    live_cache.add_bar(leg_bar)
    return live_cache


def test_materialize_exposes_the_continuous_root_id() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    model.materialize(end="2024-02-15")

    assert model.continuous_id == _ES_XCME


def test_materialize_exposes_the_schedule_front_before_migration() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    model.materialize(end="2024-02-15")

    assert model.front_leg == _ESH4


def test_front_leg_as_of_follows_the_schedule_after_migration() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    front = model.front_leg_as_of("2024-05-31")

    assert front == _ESM4


def test_materialize_exposes_the_ohlcv_frame_shape() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    model.materialize(end="2024-02-15")

    assert list(model.frame.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_front_picker_agreement_names_the_near_leg_before_regular_migration() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    assert _causal_front(port, "ES", date(2024, 2, 15)) == _ESH4
    assert model.front_leg_as_of(date(2024, 2, 15)) == _ESH4


def test_front_picker_agreement_names_the_next_leg_after_regular_migration() -> None:
    port, _native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    assert _causal_front(port, "ES", date(2024, 5, 31)) == _ESM4
    assert model.front_leg_as_of(date(2024, 5, 31)) == _ESM4


def test_front_picker_agreement_names_the_mid_leg_before_early_crossover() -> None:
    port = early_crossover_es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    assert _causal_front(port, "ES", date(2024, 4, 12)) == _ESM4
    assert model.front_leg_as_of(date(2024, 4, 12)) == _ESM4


def test_front_picker_agreement_names_the_back_leg_after_early_crossover() -> None:
    port = early_crossover_es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    assert _causal_front(port, "ES", date(2024, 5, 1)) == _ESU4
    assert model.front_leg_as_of(date(2024, 5, 1)) == _ESU4


def test_on_bar_appends_a_front_leg_bar_at_offset_zero() -> None:
    port, native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    model.materialize(end="2024-04-29")
    bar = _bar_on(native, _ESM4, date(2024, 4, 30))

    model.on_bar(bar)

    pd.testing.assert_frame_equal(
        model.frame.tail(1),
        _expected_ohlcv_row(
            "2024-05-01", open_=275.5, high=277.0, low=275.0, close=276.0, volume=1000.0
        ),
    )


def test_on_bar_keeps_the_front_leg_when_appending_current_front() -> None:
    port, native = es_port()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")
    model.materialize(end="2024-04-29")
    bar = _bar_on(native, _ESM4, date(2024, 4, 30))

    model.on_bar(bar)

    assert model.front_leg == _ESM4


def test_roll_advances_the_front() -> None:
    model = _materialized_two_roll_model()

    assert model.front_leg == _ESU4


def test_roll_records_the_rebasing_from_the_seam() -> None:
    model = _materialized_two_roll_model()

    assert model.last_rebasing.apply(100.0) == pytest.approx(121.56862745098039)


def test_roll_rematerializes_prior_closes_in_the_new_basis() -> None:
    model = _materialized_two_roll_model()
    expected = pd.Series(
        [363.5, 364.7, 365.9, 367.1, 368.4],
        index=pd.DatetimeIndex(
            ["2024-06-01", "2024-06-04", "2024-06-05", "2024-06-06", "2024-06-07"]
        ),
        name="Close",
    )

    pd.testing.assert_series_equal(model.frame.loc[expected.index, "Close"], expected)


def test_incremental_replay_across_the_roll_matches_the_one_shot_series() -> None:
    # The old front's bar triggers the roll; the new front's same-day bar
    # arrives after and closes the boundary bucket.
    model, oracle = _replayed_across_the_roll((_ESH4, _ESM4))

    pd.testing.assert_frame_equal(model.frame, oracle)


def test_replay_where_the_new_front_bar_triggers_the_roll_matches_the_one_shot() -> None:
    # The new front's bar itself triggers the roll — the boundary bucket can only
    # come from folding the trigger bar back in after the re-materialize.
    model, oracle = _replayed_across_the_roll((_ESM4, _ESH4))

    pd.testing.assert_frame_equal(model.frame, oracle)


def test_materialize_does_not_write_continuous_bars_into_a_live_cache() -> None:
    port, _native = es_port()
    live_cache = _live_cache_with_raw_bar()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    model.materialize(end=ES_END)

    assert live_cache.bars(continuous_bar_type(_ES_XCME, "1D")) == []


def test_materialize_leaves_existing_live_cache_raw_leg_bars_in_place() -> None:
    port, _native = es_port()
    live_cache = _live_cache_with_raw_bar()
    model = ContinuousContractModel(port, "ES", start=ES_START, timeframe="1D")

    model.materialize(end=ES_END)

    assert live_cache.bar_count(raw_bar_type(_ESH4, "1D")) == 1


def test_continuous_contract_model_rejects_legs_across_venues() -> None:
    catalog = FakeCatalog(
        instruments=[
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XEUR", "2024-06-21"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)
    model = ContinuousContractModel(port, "ES", start=ES_START)

    with pytest.raises(ContinuousRootVenueMismatchError, match="span multiple venues"):
        model.materialize(end=ES_END)


def test_continuous_contract_model_rejects_a_root_with_no_legs() -> None:
    catalog = FakeCatalog(
        instruments=[future("CLF4.NYMEX", "2024-01-22", underlying="CL")],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)
    model = ContinuousContractModel(port, "ES", start=ES_START)

    with pytest.raises(ContinuousRootLegsNotFoundError, match="no dated legs"):
        model.materialize(end=ES_END)
