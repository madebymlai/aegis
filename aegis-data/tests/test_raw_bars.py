from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data._ensure_coverage import CoverageInterval
from aegis_data.provider import ProviderAnswer
from aegis_data.raw_bars import CatalogCoverageGapError, RawBars
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


@dataclass
class _Provider:
    records: tuple[Bar, ...]
    requests: list[BarType] = field(default_factory=list)

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[Bar]:
        self.requests.append(bar_type)
        return ProviderAnswer.verified(self.records, oldest_verified=start)


def test_stored_and_covered_are_distinct_side_effect_free_reads(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    interval = _interval()
    catalog.replace(
        CatalogKey.for_bar(bar_type),
        interval,
        (_bar(bar_type, "2024-01-01", 10.0),),
    )
    provider = _Provider((_bar(bar_type, "2024-01-01", 20.0),))
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")

    stored = raw_bars.stored(marking, interval)

    assert stored.ohlcv["Close"].tolist() == [10.0]
    assert provider.requests == []
    with pytest.raises(CatalogCoverageGapError, match="missing") as excinfo:
        raw_bars.covered(marking, interval)

    assert excinfo.value.subject == CatalogKey.for_bar(bar_type)
    assert excinfo.value.missing == (
        CoverageInterval(interval.start_ns, interval.end_ns),
    )
    assert provider.requests == []


def test_ensure_is_a_command_and_covered_is_the_following_query(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider((_bar(bar_type, "2024-01-01", 20.0),))
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")

    result = raw_bars.ensure(marking, _interval())
    covered = raw_bars.covered(marking, _interval())

    assert result is None
    assert covered.bars == provider.records
    assert covered.ohlcv["Close"].tolist() == [20.0]
    assert provider.requests == [bar_type]


def test_record_verified_keeps_explicit_empty_time_covered(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider(())
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")
    friday = pd.Timestamp("2024-01-05", tz="UTC").value
    monday = pd.Timestamp("2024-01-08", tz="UTC").value

    raw_bars.record_verified(
        bar_type,
        CatalogInterval(friday, friday),
        (_bar(bar_type, "2024-01-05", 10.0),),
    )
    raw_bars.record_verified(
        bar_type,
        CatalogInterval(friday + 1, monday - 1),
        (),
    )
    raw_bars.record_verified(
        bar_type,
        CatalogInterval(monday, monday),
        (_bar(bar_type, "2024-01-08", 11.0),),
    )
    raw_bars.ensure(marking, CatalogInterval(friday, monday))
    covered = raw_bars.covered(marking, CatalogInterval(friday, monday))

    assert [bar.close.as_double() for bar in covered.bars] == [10.0, 11.0]
    assert provider.requests == []


def _interval() -> CatalogInterval:
    return CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-02", tz="UTC").value,
    )


def _bar(bar_type: BarType, day: str, close: float) -> Bar:
    timestamp = pd.Timestamp(day, tz="UTC").value
    return Bar(
        bar_type,
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Quantity.from_int(1),
        timestamp,
        timestamp,
    )
