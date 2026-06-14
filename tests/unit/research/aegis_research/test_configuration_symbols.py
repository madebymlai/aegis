from __future__ import annotations

import pytest

from tests.support.research.aegis_research.factories import make_data_config


def test_symbols_are_ticker_ccy_records_exposing_tickers_and_currency_map() -> None:
    cfg = make_data_config(
        symbols=[
            {"ticker": "VOOL.DE", "ccy": "EUR"},
            {"ticker": "SGLN.L", "ccy": "USD"},
        ]
    )
    assert cfg.tickers == ["VOOL.DE", "SGLN.L"]
    assert cfg.currency_by_symbol == {"VOOL.DE": "EUR", "SGLN.L": "USD"}


def test_a_bare_string_symbol_is_rejected_no_currency_no_entry() -> None:
    with pytest.raises(Exception):
        make_data_config(symbols=["SYN"])
