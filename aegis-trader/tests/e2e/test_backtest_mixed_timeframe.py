"""End-to-end mixed-timeframe Commingled Book backtests (aegis-rd-9qkr.3).

An hourly and a daily cash Sleeve run in one Nautilus engine: each Sleeve
follows its own DataContract cadence, non-due Sleeves hold their retained
targets, and coalesced due transitions produce one centrally netted order set.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.catalog import raw_bar_type
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.currency import CurrencyConversion

from aegis_data.bar_type import timeframe_to_ns
from aegis_trader.backtest import run_book_backtest
from aegis_trader.bundles.stub import StubBundleRegistry

from tests.e2e.test_backtest_catalog_runner import (
    _bar,
    _closed_orders,
    _equity,
    _verified_zero_distribution_source,
)

_HOURLY_ID = InstrumentId.from_str("FAST.XLON")
_DAILY_ID = InstrumentId.from_str("SLOW.XLON")
_SECOND_HOURLY_ID = InstrumentId.from_str("PACE.XLON")
_NS_PER_HOUR = 3_600_000_000_000
_NS_PER_DAY = 86_400_000_000_000

_MIXED_BOOK_TOML = """
base_currency = "EUR"

[[sleeves]]
name = "fast"
wheel_filename = "fast.whl"
risk_share = 0.5
group = "Floor"

[[sleeves]]
name = "slow"
wheel_filename = "slow.whl"
risk_share = 0.5
group = "Floor"
"""


class _AlternatingWeightBundle(ExecutionBundle):
    """One-instrument sleeve whose target flips every completed period, so
    every due recomputation emits an order through the zero-width band."""

    def __init__(self, instrument_id: InstrumentId, timeframe: str) -> None:
        self._instrument_id = instrument_id
        self._period_ns = timeframe_to_ns(timeframe)
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe=timeframe,
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            mark_modes={instrument_id: "LAST"},
        )
        manifest = BundleManifest(
            run_id="mixed-timeframe-synth",
            role="synth",
            candidate_key=f"mixed-{instrument_id.value}",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="alternating_weight",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={instrument_id: DriftBand.symmetric(0.0)},
            gross_cap=1.0,
            net_cap=None,
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        parity = (close.index[-1].value // self._period_ns) % 2
        weight = 0.30 if parity == 0 else 0.40
        weights = pd.DataFrame(
            {self._instrument_id: [weight] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


def _seed_hourly(catalog_path, instrument_id: InstrumentId, timestamps) -> None:
    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([_equity(instrument_id)])
    bars = [
        _bar(raw_bar_type(instrument_id, "1H"), ts, 100.0) for ts in timestamps
    ]
    # Coverage spans the whole backtest window: hours without bars are the
    # venue's closed session, not missing catalog data.
    catalog.write_data(
        bars,
        start=int(pd.Timestamp("2020-01-01", tz="UTC").value),
        end=int(pd.Timestamp("2020-01-05", tz="UTC").value),
    )
    # Distribution verification reads every instrument's raw DAILY closes,
    # so an hourly-traded instrument still carries its daily series.
    daily_bars = [
        _bar(raw_bar_type(instrument_id, "1D"), ts, 100.0)
        for ts in pd.date_range("2020-01-01", periods=4, freq="D")
    ]
    catalog.write_data(
        daily_bars,
        start=int(pd.Timestamp("2020-01-01", tz="UTC").value),
        end=int(pd.Timestamp("2020-01-05", tz="UTC").value),
    )


def _seed_daily(catalog_path, instrument_id: InstrumentId, days: int) -> None:
    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([_equity(instrument_id)])
    timestamps = pd.date_range("2020-01-01", periods=days, freq="D")
    bars = [
        _bar(raw_bar_type(instrument_id, "1D"), ts, 100.0) for ts in timestamps
    ]
    catalog.write_data(
        bars,
        start=int(pd.Timestamp("2020-01-01", tz="UTC").value),
        end=int(pd.Timestamp("2020-01-05", tz="UTC").value),
    )


def _hourly_session_timestamps(days: int) -> list[pd.Timestamp]:
    return [
        pd.Timestamp(f"2020-01-0{day} {hour:02d}:00")
        for day in range(1, days + 1)
        for hour in (10, 11, 12, 13)
    ]


def _fill_timestamps(engine: Any, instrument_id: InstrumentId) -> list[pd.Timestamp]:
    return sorted(
        pd.Timestamp(order.ts_last, tz="UTC")
        for order in _closed_orders(engine)
        if order.instrument_id == instrument_id
    )


def _run_mixed_book(tmp_path, registry_bundles, instrument_ids) -> Any:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MIXED_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_hourly(catalog_path, _HOURLY_ID, _hourly_session_timestamps(3))
    if _SECOND_HOURLY_ID in instrument_ids:
        _seed_hourly(catalog_path, _SECOND_HOURLY_ID, _hourly_session_timestamps(3))
    if _DAILY_ID in instrument_ids:
        _seed_daily(catalog_path, _DAILY_ID, 4)
    return run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=StubBundleRegistry(registry_bundles),
        data_source=_verified_zero_distribution_source(catalog_path, instrument_ids),
    )


def test_hourly_sleeve_updates_hourly_while_daily_sleeve_holds_its_period(
    tmp_path,
) -> None:
    result = _run_mixed_book(
        tmp_path,
        {
            "fast.whl": _AlternatingWeightBundle(_HOURLY_ID, "1H"),
            "slow.whl": _AlternatingWeightBundle(_DAILY_ID, "1D"),
        },
        (_HOURLY_ID, _DAILY_ID),
    )
    engine = result.engine

    hourly_fills = _fill_timestamps(engine, _HOURLY_ID)
    daily_fills = _fill_timestamps(engine, _DAILY_ID)
    try:
        # The hourly Sleeve trades within the session, at several distinct
        # intraday times; the daily Sleeve trades only on its completed days.
        intraday = {ts for ts in hourly_fills if ts.hour != 0}
        assert len(intraday) >= 4
        assert daily_fills != []
        assert all(ts.hour == 0 for ts in daily_fills)
        # Daily fills land strictly on day boundaries (+1ns re-net alert).
        assert all(ts.nanosecond == 1 for ts in daily_fills)
    finally:
        engine.dispose()


def test_simultaneous_due_transitions_coalesce_into_one_re_net(tmp_path) -> None:
    result = _run_mixed_book(
        tmp_path,
        {
            "fast.whl": _AlternatingWeightBundle(_HOURLY_ID, "1H"),
            "slow.whl": _AlternatingWeightBundle(_SECOND_HOURLY_ID, "1H"),
        },
        (_HOURLY_ID, _SECOND_HOURLY_ID),
    )
    engine = result.engine

    try:
        orders = _closed_orders(engine)
        by_timestamp: dict[int, list[Any]] = {}
        for order in orders:
            by_timestamp.setdefault(order.ts_last, []).append(order)
        assert by_timestamp, "expected coalesced re-nets to trade"
        for batch in by_timestamp.values():
            # One deterministic order set per due cluster: both due Sleeves'
            # instruments trade in the same batch, at most one order each.
            instrument_ids = [order.instrument_id for order in batch]
            assert len(instrument_ids) == len(set(instrument_ids))
            assert set(instrument_ids) == {_HOURLY_ID, _SECOND_HOURLY_ID}
    finally:
        engine.dispose()


class _QuoteMarkedHourlyBundle(ExecutionBundle):
    """A fixed-weight hourly sleeve whose leg is quote-marked (BID/ASK bars)."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        self._instrument_id = instrument_id
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1H",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            mark_modes={instrument_id: "QUOTE"},
        )
        manifest = BundleManifest(
            run_id="mixed-timeframe-synth",
            role="synth",
            candidate_key="mixed-quote",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed_weight_quote",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={instrument_id: DriftBand.symmetric(0.02)},
            gross_cap=1.0,
            net_cap=None,
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        weights = pd.DataFrame(
            {self._instrument_id: [0.25] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _MixedMarkingDataSource:
    """Hourly quote-marked leg (sided frames) beside a daily bar-marked leg."""

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> Any:
        from aegis_trader.backtest import BacktestMarketData

        if timeframe == "1H":
            bid = _sided_hourly_frame(99.95)
            ask = _sided_hourly_frame(100.05)
            return BacktestMarketData(
                instruments={_HOURLY_ID: _equity(_HOURLY_ID)},
                ohlcv={_HOURLY_ID: (bid + ask) / 2.0},
                quote_frames={_HOURLY_ID: (bid, ask)},
            )
        assert timeframe == "1D"
        days = pd.date_range("2020-01-01", periods=4, freq="D")
        daily = pd.DataFrame(
            {
                "Open": [100.0] * len(days),
                "High": [100.0] * len(days),
                "Low": [100.0] * len(days),
                "Close": [100.0] * len(days),
                "Volume": [1_000_000.0] * len(days),
            },
            index=days,
        )
        return BacktestMarketData(
            instruments={_DAILY_ID: _equity(_DAILY_ID)},
            ohlcv={_DAILY_ID: daily},
        )


def _sided_hourly_frame(price: float) -> pd.DataFrame:
    index = pd.DatetimeIndex(_hourly_session_timestamps(3))
    return pd.DataFrame(
        {
            "Open": [price] * len(index),
            "High": [price] * len(index),
            "Low": [price] * len(index),
            "Close": [price] * len(index),
            "Volume": [1_000_000.0] * len(index),
        },
        index=index,
    )


def test_quote_marked_hourly_sleeve_fills_from_its_own_bid_ask_streams(
    tmp_path,
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MIXED_BOOK_TOML)

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=tmp_path / "catalog",
        registry=StubBundleRegistry(
            {
                "fast.whl": _QuoteMarkedHourlyBundle(_HOURLY_ID),
                "slow.whl": _AlternatingWeightBundle(_DAILY_ID, "1D"),
            }
        ),
        data_source=_MixedMarkingDataSource(),
    )
    engine = result.engine

    try:
        hourly_fills = [
            order
            for order in _closed_orders(engine)
            if order.instrument_id == _HOURLY_ID
        ]
        assert hourly_fills, "quote-marked hourly sleeve produced no fills"
        # A buy against the hourly BID/ASK book fills at the ask, at an
        # intraday timestamp — the hourly quote streams drove the fill.
        first = hourly_fills[0]
        assert float(first.avg_px) == 100.05
        assert pd.Timestamp(first.ts_last, tz="UTC").hour != 0
        daily_fills = _fill_timestamps(engine, _DAILY_ID)
        assert daily_fills != []
        assert all(ts.hour == 0 for ts in daily_fills)
    finally:
        engine.dispose()
