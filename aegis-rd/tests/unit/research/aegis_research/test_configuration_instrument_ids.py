from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.support.research.aegis_research.factories import make_data_config


def test_data_config_exposes_instrument_ids_without_legacy_aliases() -> None:
    cfg = make_data_config(
        instruments=["VOOL.DE", "SGLN.L"],
        base_currency="EUR",
    )
    assert cfg.instruments == ["VOOL.DE", "SGLN.L"]
    assert cfg.native_instrument_ids == ("VOOL.DE", "SGLN.L")
    assert not hasattr(cfg, "tickers")
    assert not hasattr(cfg, "currency_by_symbol")


def test_legacy_symbols_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_data_config(symbols=[{"ticker": "SYN", "ccy": "EUR"}])
