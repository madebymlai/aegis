"""Currency parity: RD's vbt-side conversion == Nautilus' own base-currency valuation.

The catalog stores native prices; RD converts to the book's base currency vbt-side
while the trader lets Nautilus convert natively. The only thing binding the two is
this test: on a multi-currency fixture with FX *movement*, RD's converted
base-currency value of a held position must match a real Nautilus backtest's
``net_exposure * get_mark_xrate`` per bar.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from research.aegis_research.market_data.currency import build_currency_conversion
from tests.support.research.aegis_research.market_data_fixtures import (
    currency_pair_definition,
    equity_definition,
)
from tests.support.research.aegis_research.nautilus_fx_oracle import (
    nautilus_base_value_curve,
)

_QTY = 100
_AAPL = InstrumentId(symbol=Symbol("AAPL"), venue=Venue("SIM"))
_EURUSD = InstrumentId(symbol=Symbol("EUR/USD"), venue=Venue("SIM"))


def test_rd_conversion_matches_nautilus_base_value_under_fx_movement() -> None:
    index = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    native_close = pd.Series([100.0, 101.0, 103.0, 102.0, 105.0, 106.0], index=index)
    # EUR/USD moves every bar — entry rate != mark rate, so a flat rate would be wrong.
    eur_usd = pd.Series([1.10, 1.12, 1.15, 1.13, 1.18, 1.20], index=index)

    equity = equity_definition(_AAPL, "USD")
    pair = currency_pair_definition(_EURUSD)

    oracle = nautilus_base_value_curve(
        equity=equity,
        fx_pair=pair,
        native_close=native_close,
        fx_rate=eur_usd,
        quantity=_QTY,
        base_currency="EUR",
    )

    conversion = build_currency_conversion(
        instruments={equity.id: equity},
        fx_pairs={pair.id: pair},
        fx_close={pair.id: eur_usd},
        base_currency="EUR",
    )
    base_close = conversion.apply({"Close": native_close.to_frame(name=equity.id)})["Close"]
    rd_base_value = (_QTY * base_close[equity.id]).reindex(oracle.index)

    assert not oracle.empty
    pd.testing.assert_series_equal(
        rd_base_value, oracle, check_names=False, rtol=1e-9, atol=1e-6
    )


def test_parity_fixture_actually_exercises_fx_movement() -> None:
    # Guard the oracle above: converting with a *flat* rate (entry rate held all the
    # way) must NOT match Nautilus, proving the test pins moving-rate behaviour.
    index = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    native_close = pd.Series([100.0, 101.0, 103.0, 102.0, 105.0, 106.0], index=index)
    eur_usd = pd.Series([1.10, 1.12, 1.15, 1.13, 1.18, 1.20], index=index)
    flat = pd.Series(1.10, index=index)

    equity = equity_definition(_AAPL, "USD")
    pair = currency_pair_definition(_EURUSD)
    oracle = nautilus_base_value_curve(
        equity=equity, fx_pair=pair, native_close=native_close, fx_rate=eur_usd, quantity=_QTY
    )
    flat_conversion = build_currency_conversion(
        instruments={equity.id: equity},
        fx_pairs={pair.id: pair},
        fx_close={pair.id: flat},
        base_currency="EUR",
    )
    flat_base = flat_conversion.apply({"Close": native_close.to_frame(name=equity.id)})["Close"]
    flat_value = (_QTY * flat_base[equity.id]).reindex(oracle.index)

    assert not flat_value.equals(oracle)
