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
from nautilus_trader.model.currencies import EUR, GBP
from nautilus_trader.model.objects import Money
from nautilus_trader.model.data import BarType
from nautilus_trader.model.instruments import CurrencyPair

from aegis_data.store import FxPair, StoreCoverageError, write_fx_history, write_native_bars
from aegis_runtime import (
    ListedRef,
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
    run_book_backtest_from_store,
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

_COSTED_BOOK_TOML = f"""
base_currency = "EUR"

[costs]
per_share_commission = 0.01
min_commission_per_order = 1.0
max_commission_pct = 0.10
slippage_probability = 0.0
slippage_seed = 42

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""

_MARGIN_INTEREST_BOOK_TOML = f"""
base_currency = "EUR"

[costs]
per_share_commission = 0.01
min_commission_per_order = 0.0
max_commission_pct = 0.10
slippage_probability = 0.0
slippage_seed = 42

[costs.borrow]
rate = 0.036

[costs.margin_interest]
GBP = 0.06

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""

_FORCED_SLIPPAGE_BOOK_TOML = f"""
base_currency = "EUR"

[costs]
per_share_commission = 0.0
min_commission_per_order = 0.0
max_commission_pct = 0.0
slippage_probability = 1.0
slippage_seed = 42

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
        direction: str = "longonly",
    ) -> None:
        self._figi = figi
        self._weight = weight
        self._currency = currency
        self.seen_arrays: tuple[str, ...] = ()
        contract = DataContract(
            refs=(ListedRef(figi),),
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
            refs=(ListedRef(figi),),
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
            direction=direction,
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


def _flat_ohlcv() -> pd.DataFrame:
    """Constant-price daily bars: a held position does not drift, so a fixed-weight
    sleeve trades once and then sits — isolating carry (interest/borrow) from any
    drift-driven rebalance now that NAV reflects foreign-currency equity correctly."""
    index = pd.date_range("2020-01-01", periods=6, freq="D")
    flat = [100.0] * 6
    return pd.DataFrame(
        {"open": flat, "high": flat, "low": flat, "close": flat, "volume": [1000] * 6},
        index=index,
    )


def _synthetic_gapped_ohlcv() -> pd.DataFrame:
    """Daily bars that skip a weekend: Fri 2020-01-03 is followed by Mon 2020-01-06
    with no Sat/Sun bar.  The Fri→Mon step is a 3-calendar-day gap with no bar in
    between — the case a flat one-charge-per-bar financing accrual under-counts."""
    index = pd.DatetimeIndex(
        ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    )
    prices = [100.0, 101.0, 102.0, 103.0, 104.0]
    return pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices,
         "volume": [1000] * 5},
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


def _fx_must_not_be_called(base: str, quote: str, start: str, end: str) -> pd.Series:
    raise AssertionError("a pure-EUR book must not fetch FX")


def _closed_order(engine):
    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert len(fills) == 1
    return fills[0]


def _execution_fills(order) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (
            str(event.last_qty),
            str(event.last_px),
            str(event.commission),
            str(event.ts_event),
        )
        for event in order.events
        if event.__class__.__name__ == "OrderFilled"
    )


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


def test_absent_costs_backtest_keeps_cost_free_fills(tmp_path):
    """The zero-cost default preserves today's simulated fill commissions."""
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
    assert fills[0].commissions() == [Money(0, EUR)]
    engine.dispose()


def test_cost_configured_backtest_produces_fills_with_non_zero_commission(tmp_path):
    """The runner injects the Book's fee model into the simulated venue."""
    book_path = tmp_path / "book.toml"
    book_path.write_text(_COSTED_BOOK_TOML)
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
    assert fills[0].commissions() != [Money(0, EUR)]
    engine.dispose()


def test_foreign_sleeve_buy_creates_per_currency_margin_loan(tmp_path):
    """A GBP buy leaves EUR cash untouched and creates a GBP debit balance."""
    ohlcv = _synthetic_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(_COSTED_BOOK_TOML)

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="GBP", required_fx_currencies=("GBP",))}
        ),
    )

    account = engine.cache.accounts()[0]
    order = _closed_order(engine)
    traded_notional = sum(
        event.last_qty.as_double() * event.last_px.as_double()
        for event in order.events
        if event.__class__.__name__ == "OrderFilled"
    )
    commission = order.commissions()[0].as_double()

    assert account.base_currency is None
    assert account.balance_total(EUR).as_double() == pytest.approx(1_000_000.0)
    assert account.balance_total(GBP).as_double() == pytest.approx(
        -(traded_notional + commission)
    )
    engine.dispose()


def test_short_position_accrues_borrow_as_cost_not_credit(tmp_path):
    """A held short pays borrow; carry makes cash lower than sale proceeds less commission.

    Flat prices hold the short static (no drift rebalance) so the cash delta is
    pure borrow carry."""
    ohlcv = _flat_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MARGIN_INTEREST_BOOK_TOML)

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {
                _WHEEL: _FixedWeightBundle(
                    _FIGI,
                    -0.5,
                    currency="GBP",
                    required_fx_currencies=("GBP",),
                    direction="both",
                )
            }
        ),
    )

    order = _closed_order(engine)
    sale_proceeds = sum(
        event.last_qty.as_double() * event.last_px.as_double()
        for event in order.events
        if event.__class__.__name__ == "OrderFilled"
    )
    commission = order.commissions()[0].as_double()
    cash_before_borrow = sale_proceeds - commission

    assert engine.cache.accounts()[0].balance_total(GBP).as_double() < cash_before_borrow
    engine.dispose()


def test_multicurrency_book_backtest_reports_base_currency_return(tmp_path):
    """A multi-currency book (EUR base, GBP sleeve) reports a base-currency total
    return equal to its actual EUR NAV change — computed from the NAV curve, since
    Nautilus' own analyzer returns nan for a base_currency=None account.  Ties the
    reported number to the real book NAV, not just 'is finite' (aegis-rd-syp)."""
    from nautilus_trader.model.currencies import EUR

    from aegis_trader.backtest import book_return_stats
    from aegis_trader.portfolio import NautilusBookState

    ohlcv = _synthetic_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MARGIN_INTEREST_BOOK_TOML)
    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        starting_cash=1_000_000.0,
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="GBP", required_fx_currencies=("GBP",))}
        ),
    )
    # The book's true end-of-run EUR NAV (cash + foreign equity, base-converted).
    final_nav = NautilusBookState(
        portfolio=engine.portfolio, cache=engine.cache, base_currency=EUR, instr_to_figi={}
    ).nav()
    expected_return_pct = (final_nav / 1_000_000.0 - 1.0) * 100.0

    stats = book_return_stats(engine)
    # Within one day's financing accrual (~8e-3 pp): the curve samples NAV on_bar,
    # just before that bar's interest settles, so the final level leads the settled
    # NAV by the last accrual (the day-over-day returns are unaffected).
    assert stats["Total Return (%)"] == pytest.approx(expected_return_pct, abs=0.05)
    assert stats["Total Return (%)"] > 0.0  # a real, base-denominated gain (not nan)
    engine.dispose()


def test_book_starting_balances_seed_the_account(tmp_path):
    """[starting_balances] funds the simulated multi-currency account per currency:
    a declared USD balance is held even when the book trades only EUR."""
    from nautilus_trader.model.currencies import USD

    ohlcv = _synthetic_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(f"""
base_currency = "EUR"

[starting_balances]
EUR = 1_000_000.0
USD = 500_000.0

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
""")
    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )
    usd = engine.cache.accounts()[0].balances_total().get(USD)
    assert usd is not None and usd.as_double() == pytest.approx(500_000.0)
    engine.dispose()


def test_foreign_margin_loan_accrues_daily_interest(tmp_path):
    """A held GBP debit accrues configured daily margin interest."""
    ohlcv = _synthetic_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MARGIN_INTEREST_BOOK_TOML)

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="GBP", required_fx_currencies=("GBP",))}
        ),
    )

    order = _closed_order(engine)
    fills = [e for e in order.events if e.__class__.__name__ == "OrderFilled"]
    traded_notional = sum(e.last_qty.as_double() * e.last_px.as_double() for e in fills)
    commission = order.commissions()[0].as_double()
    fill_date = min(pd.Timestamp(e.ts_event) for e in fills).normalize()
    last_date = ohlcv.index[-1].normalize()
    interest = (
        -engine.cache.accounts()[0].balance_total(GBP).as_double()
        - traded_notional
        - commission
    )

    # Held from the fill tick (01-03) to the last bar (01-06): entry day + one per
    # calendar day after = 4 days of interest on the GBP debit (principal + the
    # commission the loan funds), within compounding tolerance.
    accrual_days = (last_date - fill_date).days + 1
    expected_interest = (traded_notional + commission) * 0.06 * accrual_days / 360.0
    assert interest == pytest.approx(expected_interest, rel=1e-3)
    engine.dispose()


def test_margin_interest_accrues_calendar_days_across_a_market_gap(tmp_path):
    """Financing is a calendar-day carry, not one charge per bar: a GBP loan held
    across a weekend (no Sat/Sun bars) accrues the full elapsed span, so the
    Fri→Mon step counts 3 days — not 1."""
    ohlcv = _synthetic_gapped_ohlcv()
    book_path = tmp_path / "book.toml"
    book_path.write_text(_MARGIN_INTEREST_BOOK_TOML)

    engine = run_book_backtest(
        str(book_path),
        start="2020-01-01",
        end="2020-01-08",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="GBP", required_fx_currencies=("GBP",))}
        ),
    )

    order = _closed_order(engine)
    fills = [e for e in order.events if e.__class__.__name__ == "OrderFilled"]
    principal = sum(e.last_qty.as_double() * e.last_px.as_double() for e in fills)
    commission = order.commissions()[0].as_double()
    fill_date = min(pd.Timestamp(e.ts_event) for e in fills).normalize()
    last_date = ohlcv.index[-1].normalize()
    interest = (
        -engine.cache.accounts()[0].balance_total(GBP).as_double() - principal - commission
    )

    # The loan opens on the fill tick (Fri 01-03) and is held to the last bar
    # (Tue 01-07): one charge for the entry day plus one per calendar day after,
    # weekend included. A flat per-bar accrual would skip Sat/Sun and charge 3.
    assert fill_date.date().isoformat() == "2020-01-03"
    accrual_days = (last_date - fill_date).days + 1  # 4 nights + entry day = 5
    debit = principal + commission  # the loan funds the commission too
    expected_interest = debit * 0.06 * accrual_days / 360.0
    # rel tolerance absorbs intraday compounding of interest onto the debit; the
    # assertion pins the calendar-day count (5), which the bug undercounts to 3.
    assert interest == pytest.approx(expected_interest, rel=1e-3)
    engine.dispose()


def test_foreign_leg_commission_matches_base_leg_without_fx_fee_fold(tmp_path):
    """Commission is currency-agnostic; FX cost moves to margin interest later."""
    ohlcv = _synthetic_ohlcv()
    base_path = tmp_path / "base" / "book.toml"
    base_path.parent.mkdir()
    base_path.write_text(_MARGIN_INTEREST_BOOK_TOML)
    foreign_path = tmp_path / "foreign" / "book.toml"
    foreign_path.parent.mkdir()
    foreign_path.write_text(_MARGIN_INTEREST_BOOK_TOML)

    base_engine = run_book_backtest(
        str(base_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )
    foreign_engine = run_book_backtest(
        str(foreign_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=lambda base, quote, start, end: pd.Series(1.0, index=ohlcv.index),
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="GBP", required_fx_currencies=("GBP",))}
        ),
    )

    base_commission = _closed_order(base_engine).commissions()[0].as_double()
    foreign_commission = _closed_order(foreign_engine).commissions()[0].as_double()

    assert foreign_commission == pytest.approx(base_commission)
    base_engine.dispose()
    foreign_engine.dispose()


def test_pinned_slippage_moves_fill_price_one_tick(tmp_path):
    """With prob_slippage=1.0 a buy fill is one tick worse than zero slippage."""
    ohlcv = _synthetic_ohlcv()
    no_slip_path = tmp_path / "no_slip" / "book.toml"
    no_slip_path.parent.mkdir()
    no_slip_path.write_text(_BOOK_TOML)
    slip_path = tmp_path / "slip" / "book.toml"
    slip_path.parent.mkdir()
    slip_path.write_text(_FORCED_SLIPPAGE_BOOK_TOML)

    no_slip_engine = run_book_backtest(
        str(no_slip_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )
    slip_engine = run_book_backtest(
        str(slip_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )

    assert _closed_order(slip_engine).avg_px - _closed_order(no_slip_engine).avg_px == pytest.approx(0.01)
    no_slip_engine.dispose()
    slip_engine.dispose()


def test_costed_backtest_fill_path_is_deterministic_with_pinned_seed(tmp_path):
    """Same cost config, including slippage seed, yields identical fill facts."""
    ohlcv = _synthetic_ohlcv()
    first_path = tmp_path / "first" / "book.toml"
    first_path.parent.mkdir()
    first_path.write_text(_FORCED_SLIPPAGE_BOOK_TOML)
    second_path = tmp_path / "second" / "book.toml"
    second_path.parent.mkdir()
    second_path.write_text(_FORCED_SLIPPAGE_BOOK_TOML)

    first_engine = run_book_backtest(
        str(first_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )
    second_engine = run_book_backtest(
        str(second_path),
        start="2020-01-01",
        end="2020-01-07",
        fetch_ohlcv=lambda request: ohlcv,
        fetch_fx=_fx_must_not_be_called,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )

    assert _execution_fills(_closed_order(first_engine)) == _execution_fills(_closed_order(second_engine))
    first_engine.dispose()
    second_engine.dispose()


def test_run_book_backtest_from_store_feeds_preseeded_listed_bars(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    write_native_bars(ListedRef(_FIGI), "1D", _synthetic_ohlcv(), store_dir=tmp_path)

    engine = run_book_backtest_from_store(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        store_dir=tmp_path,
        registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
    )

    fills = [order for order in engine.cache.orders() if order.is_closed]
    engine.dispose()
    assert len(fills) == 1


def test_run_book_backtest_from_store_fails_closed_on_missing_listed_bars(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)

    with pytest.raises(StoreCoverageError) as exc:
        run_book_backtest_from_store(
            str(book_path),
            start="2020-01-01",
            end="2020-01-07",
            store_dir=tmp_path,
            registry=StubBundleRegistry({_WHEEL: _FixedWeightBundle(_FIGI, 0.5)}),
        )

    assert _FIGI in str(exc.value)


def test_run_book_backtest_from_store_reads_required_fx_history(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    ohlcv = _synthetic_ohlcv()
    fx = pd.Series([1.10, 1.20, 1.30, 1.40], index=pd.bdate_range("2020-01-01", periods=4))
    write_native_bars(ListedRef(_FIGI), "1D", ohlcv, store_dir=tmp_path)
    write_fx_history(FxPair("EUR", "USD"), "1D", fx, store_dir=tmp_path)

    engine = run_book_backtest_from_store(
        str(book_path),
        start="2020-01-01",
        end="2020-01-07",
        store_dir=tmp_path,
        registry=StubBundleRegistry(
            {_WHEEL: _FixedWeightBundle(_FIGI, 0.5, currency="USD", required_fx_currencies=("USD",))}
        ),
    )
    pair = next(i for i in engine.cache.instruments() if isinstance(i, CurrencyPair))
    bids = sorted(round(float(q.bid_price), 5) for q in engine.cache.quote_ticks(pair.id))
    engine.dispose()

    assert bids == [1.10, 1.20, 1.30, 1.30, 1.30, 1.40]


def test_run_book_backtest_from_store_fails_closed_on_missing_fx_history(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    write_native_bars(ListedRef(_FIGI), "1D", _synthetic_ohlcv(), store_dir=tmp_path)

    with pytest.raises(StoreCoverageError) as exc:
        run_book_backtest_from_store(
            str(book_path),
            start="2020-01-01",
            end="2020-01-07",
            store_dir=tmp_path,
            registry=StubBundleRegistry(
                {
                    _WHEEL: _FixedWeightBundle(
                        _FIGI, 0.5, currency="USD", required_fx_currencies=("USD",)
                    )
                }
            ),
        )

    assert "EUR/USD" in str(exc.value)


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
