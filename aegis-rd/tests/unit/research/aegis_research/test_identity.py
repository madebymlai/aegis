"""``resolved_instruments`` pairs each tradeable with its bare ``data.futures`` root.

It is the single source of the native→future ordering and the id↔root pairing that the
contract instrument ids and the per-instrument drift-band map are both derived from.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from aegis_data.catalog import ResolvedContinuousRoot
from aegis_data.roll import DatedContract
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import TypeAdapter

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data import identity as identity_module
from research.aegis_research.market_data.identity import resolved_instruments

_DATA = TypeAdapter(DataConfig)


def test_resolved_instruments_does_not_open_catalog_without_futures(monkeypatch) -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )

    def fail_if_called(_path):
        raise AssertionError("catalog should not be opened without futures")

    monkeypatch.setattr(identity_module, "catalog_data_port", fail_if_called)

    assert resolved_instruments(SimpleNamespace(data=data)) == (
        (InstrumentId.from_str("AAPL.NASDAQ"), None),
    )


def test_resolved_instruments_pairs_continuous_ids_with_their_root(monkeypatch) -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES"],
            "path": "/catalog",
            "timeframe": "1D",
        }
    )
    calls: list[str] = []

    class FakePort:
        def resolve_continuous(self, root: str) -> ResolvedContinuousRoot:
            calls.append(root)
            return ResolvedContinuousRoot(
                InstrumentId.from_str("ES.XCME"),
                (DatedContract("ESH4.XCME", date(2024, 3, 15)),),
            )

    def fake_catalog_data_port(path):
        assert path == "/catalog"
        return FakePort()

    monkeypatch.setattr(identity_module, "catalog_data_port", fake_catalog_data_port)

    assert resolved_instruments(SimpleNamespace(data=data)) == (
        (InstrumentId.from_str("AAPL.NASDAQ"), None),
        (InstrumentId.from_str("ES.XCME"), "ES"),
    )
    assert calls == ["ES"]
