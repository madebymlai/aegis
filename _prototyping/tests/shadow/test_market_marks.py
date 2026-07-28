from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from _prototyping.merger.shadow import (
    AegisCatalogMarkSource,
    EventObservation,
    EventStatus,
)


class _Catalog:
    def __init__(self, frames) -> None:
        self._frames = frames

    def load_window(self, request):
        return SimpleNamespace(ohlcv=self._frames)


def test_catalog_mark_source_prices_only_explicit_instrument_ids() -> None:
    dates = pd.bdate_range("2025-10-01", "2026-02-02")
    market_close = 100.0 * np.exp(np.arange(len(dates)) * 0.001)
    target_close = 9.0 * np.exp(np.arange(len(dates)) * 0.0015)
    target_close[dates >= "2026-01-03"] = 10.0
    target_id = InstrumentId.from_str("D01.XNYS")
    market_id = InstrumentId.from_str("SPY.ARCA")
    frames = {
        target_id: pd.DataFrame({"Close": target_close, "Volume": 2_000_000.0}, index=dates),
        market_id: pd.DataFrame({"Close": market_close, "Volume": 10_000_000.0}, index=dates),
    }
    event = EventObservation(
        event_id="1:announcement",
        instrument_id="D01.XNYS",
        target_cik="1",
        ticker="D01",
        agreement_accession="announcement",
        agreement_date="2026-01-02",
        observed_at="2026-01-03T12:00:00+00:00",
        status=EventStatus.ANNOUNCED,
        offer_price=10.20,
        source_accession="announcement",
        source_url="https://example.test/announcement",
        evidence="Fixed-cash merger.",
    )
    source = AegisCatalogMarkSource(
        0.04,
        port=_Catalog(frames),
    )

    batch = source.load(
        (event,),
        as_of=datetime(2026, 2, 2, 22, tzinfo=UTC),
    )

    assert batch.unavailable == ()
    assert batch.marks[0].ticker == "D01"
    assert batch.marks[0].close == 10.0
    assert batch.marks[0].annual_cash_rate == 0.04
    assert len(batch.marks[0].preannouncement_closes) == 20
    assert batch.marks[0].preannouncement_closes[-1] == batch.marks[0].preannouncement_close
