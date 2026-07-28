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


def test_declared_marking_resolver_marks_exchange_legs_mid_by_section_membership() -> None:
    """No FX heuristic (aegis-rd-t2kc): the ``exchange:`` section IS the MID
    declaration; a tradeable resolves LAST unless its token declares otherwise."""
    from aegis_data.marking import MarkMode
    from nautilus_trader.model.identifiers import InstrumentId

    config = make_data_config(
        instruments=["UEQC.XETR:QUOTE", "VUSA.XLON"],
        exchange=["EUR/USD.IDEALPRO"],
    )

    resolver = config.marking_resolver()

    assert resolver.resolve(InstrumentId.from_str("EUR/USD.IDEALPRO"), "1D").mode is MarkMode.MID
    assert resolver.resolve(InstrumentId.from_str("UEQC.XETR"), "1D").mode is MarkMode.QUOTE
    assert resolver.resolve(InstrumentId.from_str("VUSA.XLON"), "1D").mode is MarkMode.LAST
