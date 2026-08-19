"""ResolvedBook construction: the public seam for the run-constant book facts.

The factory owns all three resolutions — the FX-adjusted fee series, the
instrument → DriftBand map (via the drift-bands authority), and the futures
roots — so an incoherent config/facts pairing cannot exist as a value.
"""

from __future__ import annotations

import pandas as pd
from aegis_runtime import DriftBand
from aegis_runtime.domain.currency import CurrencyConversion
from nautilus_trader.model.identifiers import InstrumentId
from pandas.testing import assert_series_equal

from research.aegis_research.configuration import InstrumentBandConfig
from research.aegis_research.instrument_resolution import (
    InstrumentResolution,
    TradeableInstrument,
)
from research.aegis_research.portfolio_simulation import ResolvedBook
from tests.support.research.aegis_research.factories import (
    make_data_config,
    make_portfolio_config,
    make_run_config,
    make_run_data,
)


def test_foreign_legs_pay_the_conversion_cost_base_legs_do_not() -> None:
    vool = _id("VOOL.DE")
    sgln = _id("SGLN.L")
    config = make_run_config(
        data=make_data_config(instruments=["VOOL.DE", "SGLN.L"]),
        portfolio=make_portfolio_config(
            fees=0.0005, fx_conversion_cost=0.0003, base_currency="EUR"
        ),
    )
    conversion = CurrencyConversion({}, currency_by_instrument_id={vool: "EUR", sgln: "USD"})

    book = ResolvedBook.resolve(config.portfolio, _run_data(config, conversion))

    assert_series_equal(book.fees_by_symbol, pd.Series({vool: 0.0005, sgln: 0.0008}))


def test_gbp_minor_unit_leg_is_foreign_and_pays_the_conversion_cost() -> None:
    gbus = _id("GBUS.L")
    config = make_run_config(
        data=make_data_config(instruments=["GBUS.L"]),
        portfolio=make_portfolio_config(
            fees=0.0005, fx_conversion_cost=0.0003, base_currency="EUR"
        ),
    )
    conversion = CurrencyConversion({}, currency_by_instrument_id={gbus: "GBp"})

    book = ResolvedBook.resolve(config.portfolio, _run_data(config, conversion))

    assert_series_equal(book.fees_by_symbol, pd.Series({gbus: 0.0008}))


def test_single_currency_book_derives_a_uniform_no_op_fee_series() -> None:
    # No conversion means every leg reads as base: the base fee everywhere,
    # a no-op series rather than a second code path.
    config = make_run_config(
        data=make_data_config(instruments=["VOOL.DE", "SGLN.L"]),
        portfolio=make_portfolio_config(fees=0.0005, fx_conversion_cost=0.0003),
    )

    book = ResolvedBook.resolve(config.portfolio, _run_data(config))

    expected = pd.Series({_id("VOOL.DE"): 0.0005, _id("SGLN.L"): 0.0005})
    assert_series_equal(book.fees_by_symbol, expected)


def test_bands_resolve_through_the_drift_bands_authority() -> None:
    # An overridden tradeable gates at its own band (destination inheriting the
    # sleeve-wide fraction); an unset one falls to the sleeve default.
    config = make_run_config(
        data=make_data_config(instruments=["SYN.XNAS", "OTHER.XNAS"]),
        portfolio=make_portfolio_config(
            band_up=0.05,
            band_down=0.03,
            band_overrides={"SYN.XNAS": InstrumentBandConfig(up=0.10, down=0.08)},
        ),
    )

    book = ResolvedBook.resolve(config.portfolio, _run_data(config))

    assert book.instrument_bands == {
        _id("SYN.XNAS"): DriftBand(up=0.10, down=0.08, destination_fraction=1.0),
        _id("OTHER.XNAS"): DriftBand(up=0.05, down=0.03, destination_fraction=1.0),
    }


def test_carries_the_declared_portfolio_config() -> None:
    config = make_run_config()

    book = ResolvedBook.resolve(config.portfolio, _run_data(config))

    assert book.config is config.portfolio


def test_futures_roots_read_off_the_data_config() -> None:
    config = make_run_config()

    book = ResolvedBook.resolve(config.portfolio, _run_data(config))

    assert book.futures_roots == ()


def test_resolve_consumes_the_complete_run_data_tradeable_universe() -> None:
    aapl = _id("AAPL.XNAS")
    es = _id("ES.XCME")
    resolution = InstrumentResolution(
        (
            TradeableInstrument(aapl),
            TradeableInstrument(es, continuous_root="ES"),
        )
    )
    conversion = CurrencyConversion(
        {},
        currency_by_instrument_id={aapl: "EUR", es: "USD"},
    )
    run_data = make_run_data(
        instrument_resolution=resolution,
        currency_conversion=conversion,
        size_increment_by_instrument={aapl: 1.0, es: 0.25},
        multiplier_by_instrument={aapl: 1.0, es: 50.0},
    )
    portfolio = make_portfolio_config(
        fees=0.0005,
        fx_conversion_cost=0.0003,
        base_currency="EUR",
        band_overrides={"ES": InstrumentBandConfig(up=0.10, down=0.08)},
    )

    book = ResolvedBook.resolve(portfolio, run_data)

    assert_series_equal(book.fees_by_symbol, pd.Series({aapl: 0.0005, es: 0.0008}))
    assert book.instrument_bands == resolution.instrument_bands(portfolio)
    assert book.futures_roots == ("ES",)
    assert book.size_increment_by_instrument == {aapl: 1.0, es: 0.25}
    assert book.multiplier_by_instrument == {aapl: 1.0, es: 50.0}


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _run_data(config, conversion: CurrencyConversion | None = None):
    resolution = InstrumentResolution(
        tuple(TradeableInstrument(_id(value)) for value in config.data.instruments)
    )
    resolved_conversion = conversion or CurrencyConversion(
        {},
        currency_by_instrument_id=dict.fromkeys(
            resolution.instrument_ids,
            config.portfolio.base_currency,
        ),
    )
    return make_run_data(
        instrument_resolution=resolution,
        currency_conversion=resolved_conversion,
    )
