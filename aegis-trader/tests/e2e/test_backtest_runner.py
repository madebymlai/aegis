"""End-to-end test for the commingled-book backtest runner.

``run_book_backtest`` composes the whole offline path: resolve each sleeve's
bundle through the registry, build instruments + bars from injected fetchers,
feed a ``BacktestEngine``, and run the overlay.  The registry and fetchers are
injected, so the run is exercised here without a real wheel or the network: a
``StubBundleRegistry`` owns a synthetic single-sleeve bundle and the OHLCV is a
fixed in-memory frame.

One BacktestEngine per process (Rust runtime global state) — the e2e conftest
forks each test, so this builds its own engine freely.
"""

from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.data import BarType
from nautilus_trader.model.instruments import CurrencyPair

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.backtest import (
    BarRequest,
    ContractDataError,
    FxDataError,
    run_book_backtest,
)
from aegis_trader.bundles.stub import StubBundleRegistry

_FIGI = "BBG000B9XRY4"
_WHEEL = "synth-trend.whl"

_BOOK_TOML = f"""
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""


class _FixedWeightBundle(ExecutionBundle):
    """A bundle that always holds a fixed weight on a single EUR FIGI."""

    def __init__(
        self,
        figi: str,
        weight: float,
        required_arrays: tuple[str, ...] = ("Close",),
        timeframe: str = "1D",
        currency: str = "EUR",
        required_fx_currencies: tuple[str, ...] = (),
    ) -> None:
        self._figi = figi
        self._weight = weight
        self._currency = currency
        self.seen_arrays: tuple[str, ...] = ()
        contract = DataContract(
            figis=(figi,),
            required_arrays=required_arrays,
            base_currency="EUR",
            required_fx_currencies=required_fx_currencies,
            timeframe=timeframe,
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id=f"synth-{figi}",
            role="synth",
            candidate_key=f"synth-{figi}-key",
            component_source_hashes={},
            figis=(figi,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="synth_strat",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            gross_cap=1.0,
            net_cap=None,
            direction="both",
            symbols=(figi,),
            currency_by_symbol={figi: self._currency},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        prices: MarketDataBundle,
        *,
        fx_series: dict[str, pd.Series] | None = None,
    ) -> pd.DataFrame:
        self.seen_arrays = tuple(prices.arrays.keys())
        close = prices.array("Close")
        df = pd.DataFrame({self._figi: [self._weight] * len(close)}, index=close.index)
        df.columns.name = "figi"
        return df


def _synthetic_ohlcv() -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=6, freq="D")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "high": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "volume": [1000] * 6,
        },
        index=index,
    )


def _synthetic_intraday_ohlcv() -> pd.DataFrame:
    index = pd.date_range("2020-01-01 09:30", periods=6, freq="15min")
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    return pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices,
         "volume": [1000] * 6},
        index=index,
    )


def _fx_must_not_be_called(base: str, quote: str, start: str, end: str) -> float:
    raise AssertionError("a pure-EUR book must not fetch FX")


def test_run_book_backtest_runs_the_overlay_through_the_injected_registry(tmp_path):
    """The runner resolves the sleeve via the injected registry and runs to a fill."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)})
    ohlcv = _synthetic_ohlcv()

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=registry,
    )

    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert len(fills) == 1
    engine.dispose()


def test_run_book_backtest_asks_the_fetcher_for_each_contracts_required_arrays(tmp_path):
    """The runner builds each fetch request from the sleeve's DataContract:
    the provider ticker and exactly the arrays the contract declares."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)})
    ohlcv = _synthetic_ohlcv()
    seen: list[BarRequest] = []

    def spy(request: BarRequest) -> pd.DataFrame:
        seen.append(request)
        return ohlcv

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=spy,
        fetch_fx=_fx_must_not_be_called,
        registry=registry,
    )
    engine.dispose()

    assert [r.ticker for r in seen] == [_FIGI]
    assert seen[0].required_arrays == ("Close",)


def test_overlay_feeds_compute_weights_every_contract_required_array(tmp_path):
    """The overlay assembles a MarketDataBundle with every array the contract
    declares (not just Close), sourced from the engine's buffered bars."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(_FIGI, 0.5, required_arrays=("Close", "Volume"))
    registry = StubBundleRegistry({_WHEEL: bundle})
    ohlcv = _synthetic_ohlcv()

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=registry,
    )
    engine.dispose()

    assert set(bundle.seen_arrays) == {"Close", "Volume"}


def test_run_book_backtest_loads_and_subscribes_at_the_contract_timeframe(tmp_path):
    """A non-daily contract: the engine receives bars of the matching BarType and
    the overlay (subscribing + detecting periods at that timeframe) rebalances to
    a fill — both the LOAD and SUBSCRIBE sides honor the contract timeframe."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = StubBundleRegistry(
        {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, timeframe="15min")}
    )
    ohlcv = _synthetic_intraday_ohlcv()

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-02",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=registry,
    )

    intraday = BarType.from_str(f"{_FIGI}.SIM-15-MINUTE-LAST-EXTERNAL")
    assert len(engine.cache.bars(intraday)) > 0
    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert len(fills) >= 1
    engine.dispose()


def test_run_book_backtest_fails_closed_when_a_required_array_is_missing(tmp_path):
    """Fetched data missing a contract-required array fails closed, naming the
    sleeve/FIGI and the missing array; no engine run proceeds."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(_FIGI, 0.5, required_arrays=("Close", "Volume"))
    registry = StubBundleRegistry({_WHEEL: bundle})
    no_volume = _synthetic_ohlcv().drop(columns=["volume"])

    with pytest.raises(ContractDataError) as exc:
        run_book_backtest(
            str(book_path),
            start="2020-01-01",
            end="2020-01-07",
            fetch_ohlcv=lambda request: no_volume,
            fetch_fx=_fx_must_not_be_called,
            registry=registry,
        )

    assert _FIGI in str(exc.value)
    assert "Volume" in str(exc.value)


def test_run_book_backtest_fails_closed_when_lookback_is_not_satisfied(tmp_path):
    """Fewer than lookback_bars + 1 fetched rows fails closed (no partial run)."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(_FIGI, 0.5)  # lookback_bars=1 -> needs >= 2 rows
    registry = StubBundleRegistry({_WHEEL: bundle})
    one_row = _synthetic_ohlcv().iloc[:1]

    with pytest.raises(ContractDataError) as exc:
        run_book_backtest(
            str(book_path),
            start="2020-01-01",
            end="2020-01-07",
            fetch_ohlcv=lambda request: one_row,
            fetch_fx=_fx_must_not_be_called,
            registry=registry,
        )

    assert _FIGI in str(exc.value)


def test_run_book_backtest_values_foreign_positions_without_xrate_noise(capfd, tmp_path):
    """A non-base (USD) sleeve is valued in EUR via the mark xrate the runner
    sets — the portfolio must not spam 'Cannot calculate exchange rate' because
    it tried to derive FX from quote ticks that a bar-fed backtest never has."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(
        _FIGI, 0.5, currency="USD", required_fx_currencies=("USD",)
    )
    registry = StubBundleRegistry({_WHEEL: bundle})
    ohlcv = _synthetic_ohlcv()

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.10, index=ohlcv.index),
        registry=registry,
    )
    engine.dispose()

    captured = capfd.readouterr()
    assert "Cannot calculate exchange rate" not in (captured.out + captured.err)


def test_run_book_backtest_feeds_time_varying_fx_quotes(tmp_path):
    """An FxFetcher returning a per-date series produces FX quotes whose rate
    changes over time — not one flat rate held across the whole window."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(
        _FIGI, 0.5, currency="USD", required_fx_currencies=("USD",)
    )
    registry = StubBundleRegistry({_WHEEL: bundle})
    ohlcv = _synthetic_ohlcv()  # 6 daily bars, 2020-01-01..06
    fx = pd.Series([1.10, 1.20, 1.30, 1.40, 1.50, 1.60], index=ohlcv.index)

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: fx,
        registry=registry,
    )
    pairs = [i for i in engine.cache.instruments() if isinstance(i, CurrencyPair)]
    bids = {round(float(q.bid_price), 5) for q in engine.cache.quote_ticks(pairs[0].id)}
    engine.dispose()

    assert len(pairs) == 1
    assert bids == {1.10, 1.20, 1.30, 1.40, 1.50, 1.60}


def test_run_book_backtest_aligns_sparse_fx_to_the_bar_timeline(tmp_path):
    """A coarse FX series is forward-filled onto the bar timeline, so every bar
    date resolves a current rate — not only the dates the FX provider quoted."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(
        _FIGI, 0.5, currency="USD", required_fx_currencies=("USD",)
    )
    registry = StubBundleRegistry({_WHEEL: bundle})
    ohlcv = _synthetic_ohlcv()  # 6 daily bars, 2020-01-01..06
    sparse = pd.Series([1.10, 1.40], index=ohlcv.index[[0, 3]])  # quoted on 2 of 6

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: sparse,
        registry=registry,
    )
    pair = next(i for i in engine.cache.instruments() if isinstance(i, CurrencyPair))
    bids = sorted(round(float(q.bid_price), 5) for q in engine.cache.quote_ticks(pair.id))
    engine.dispose()

    # one quote per bar date, forward-filled across the gap
    assert bids == [1.10, 1.10, 1.10, 1.40, 1.40, 1.40]


def test_run_book_backtest_fails_closed_when_fx_does_not_cover_the_window(tmp_path):
    """An FX series starting after the first bar leaves a front-edge gap ffill
    cannot bridge; the runner fails closed instead of valuing on a fabricated rate."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    bundle = _FixedWeightBundle(
        _FIGI, 0.5, currency="USD", required_fx_currencies=("USD",)
    )
    registry = StubBundleRegistry({_WHEEL: bundle})
    ohlcv = _synthetic_ohlcv()  # 6 daily bars, 2020-01-01..06
    late_fx = pd.Series([1.40, 1.50, 1.60], index=ohlcv.index[3:])  # first 3 uncovered

    with pytest.raises(FxDataError) as exc:
        run_book_backtest(
            str(book_path),
            start="2020-01-01",
            end="2020-01-07",
            fetch_ohlcv=lambda request: ohlcv,
            fetch_fx=lambda base, quote, start, end: late_fx,
            registry=registry,
        )

    assert "EUR/USD" in str(exc.value)
