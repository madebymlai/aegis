"""Custom Data module behavior through its public interface."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.custom_data import (
    CustomDataProviderPort,
    FixtureRecord,
    ServedCustomData,
    ingest,
    records,
)

_INSTRUMENT = InstrumentId.from_str("SPY.ARCA")


@dataclass
class _Provider(CustomDataProviderPort[FixtureRecord]):
    available: tuple[FixtureRecord, ...]
    served_from: pd.Timestamp | None = None
    requests: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        self.requests.append((start, end))
        selected = tuple(
            record
            for record in self.available
            if record.instrument_id == instrument_id
            and start.value <= record.ts_event <= end.value
        )
        return ServedCustomData(selected, self.served_from or start)


def test_ingest_is_idempotent_and_records_round_trip_typed(tmp_path: Path) -> None:
    provider = _Provider((_record("2024-01-02", 7.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers=(provider,),
        catalog_path=tmp_path,
    )
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers=(provider,),
        catalog_path=tmp_path,
    )
    stored = records(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog_path=tmp_path,
    )

    assert provider.requests == [(_utc("2024-01-01"), _utc("2024-01-03"))]
    assert stored == (_record("2024-01-02", 7.0),)
    assert isinstance(stored[0], FixtureRecord)


def test_ingest_fills_providers_in_declared_order(tmp_path: Path) -> None:
    first = _Provider(
        (_record("2024-01-08", 8.0),),
        served_from=_utc("2024-01-06"),
    )
    second = _Provider((_record("2024-01-02", 2.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-10"),
        providers=(first, second),
        catalog_path=tmp_path,
    )

    assert first.requests == [(_utc("2024-01-01"), _utc("2024-01-10"))]
    assert second.requests == [
        (_utc("2024-01-01"), pd.Timestamp(_utc("2024-01-06").value - 1, tz="UTC"))
    ]
    assert records(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-10"),
        catalog_path=tmp_path,
    ) == (_record("2024-01-02", 2.0), _record("2024-01-08", 8.0))


def test_ingest_fills_only_an_interior_native_gap(tmp_path: Path) -> None:
    seed = _Provider(
        (_record("2024-01-02", 2.0), _record("2024-01-08", 8.0))
    )
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers=(seed,),
        catalog_path=tmp_path,
    )
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-07"),
        end=_utc("2024-01-10"),
        providers=(seed,),
        catalog_path=tmp_path,
    )
    healer = _Provider((_record("2024-01-05", 5.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-10"),
        providers=(healer,),
        catalog_path=tmp_path,
    )

    assert healer.requests == [
        (
            pd.Timestamp(_utc("2024-01-03").value + 1, tz="UTC"),
            pd.Timestamp(_utc("2024-01-07").value - 1, tz="UTC"),
        )
    ]


def _record(day: str, value: float) -> FixtureRecord:
    timestamp = _utc(day).value
    return FixtureRecord(
        timestamp,
        timestamp,
        instrument_id=_INSTRUMENT,
        value=value,
        provider="fixture",
    )


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")
