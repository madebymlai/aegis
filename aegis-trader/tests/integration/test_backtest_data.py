"""Integration tests for synthetic FX quote construction."""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.instruments import CurrencyPair

from aegis_trader.data import build_currency_pair, wrangle_fx_quotes


def test_wrangle_fx_quotes_uses_the_pair_instrument() -> None:
    pair, quotes = _wrangled_fx_quotes()

    assert (quotes[0].instrument_id, quotes[1].instrument_id) == (pair.id, pair.id)


def test_wrangle_fx_quotes_builds_mid_prices() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        str(quotes[0].bid_price),
        str(quotes[0].ask_price),
        str(quotes[1].bid_price),
        str(quotes[1].ask_price),
    ) == ("1.08123", "1.08123", "1.08234", "1.08234")


def test_wrangle_fx_quotes_uses_precision_correct_default_sizes() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        str(quotes[0].bid_size),
        str(quotes[0].ask_size),
        quotes[0].bid_size.precision,
        quotes[0].ask_size.precision,
        str(quotes[1].bid_size),
        str(quotes[1].ask_size),
        quotes[1].bid_size.precision,
        quotes[1].ask_size.precision,
    ) == ("1000000", "1000000", 0, 0, "1000000", "1000000", 0, 0)


def test_wrangle_fx_quotes_preserves_event_and_init_timestamps() -> None:
    _pair, quotes = _wrangled_fx_quotes()

    assert (
        quotes[0].ts_event,
        quotes[0].ts_init,
        quotes[1].ts_event,
        quotes[1].ts_init,
    ) == (
        1_704_153_600_000_000_000,
        1_704_153_600_000_000_000,
        1_704_240_000_000_000_000,
        1_704_240_000_000_000_000,
    )


def _wrangled_fx_quotes() -> tuple[CurrencyPair, list[QuoteTick]]:
    pair = build_currency_pair("EUR", "USD", "IDEALPRO")
    rates = pd.Series(
        [1.08123, 1.08234],
        index=pd.to_datetime(["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"]),
    )
    return pair, wrangle_fx_quotes(pair, rates)
