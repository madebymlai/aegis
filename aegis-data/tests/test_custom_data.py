"""Custom Data module behavior through its public interface."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.catalog import CatalogCoverageGapError, GapFillProviderError
from aegis_data.custom_data import (
    CustomDataProviderPort,
    UnknownCustomArrayError,
    UnknownCustomDataRecordError,
    arrays,
    capture,
    correct,
    coverage,
    ensure_arrays,
    ingest,
    records,
    records_for_arrays,
)
from aegis_data.provider import ProviderAnswer
from aegis_data.distributions import Distribution
from aegis_data.storage import Catalog
from tests.support.custom_data import FIXTURE_CUSTOM_DATA_KINDS, FixtureRecord

_INSTRUMENT = InstrumentId.from_str("SPY.ARCA")


def test_distribution_is_not_a_custom_array_record_kind(tmp_path: Path) -> None:
    with pytest.raises(UnknownCustomDataRecordError, match="Distribution"):
        records(
            Distribution,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-03"),
            catalog=Catalog.open(tmp_path),
        )


@dataclass
class _Provider(CustomDataProviderPort[FixtureRecord]):
    available: tuple[FixtureRecord, ...]
    oldest_verified: pd.Timestamp | None = None
    requests: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[FixtureRecord]:
        self.requests.append((start, end))
        selected = tuple(
            record
            for record in self.available
            if record.instrument_id == instrument_id
            and start.value <= record.ts_event <= end.value
        )
        return ProviderAnswer(selected, self.oldest_verified or start)


@dataclass
class _ForeignRecordProvider(CustomDataProviderPort[FixtureRecord]):
    """A provider that answers with a record belonging to another instrument."""

    foreign: FixtureRecord

    def request_records(
        self,
        _instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[FixtureRecord]:
        del end
        return ProviderAnswer((self.foreign,), start)


def test_ingest_reports_a_foreign_provider_record_as_a_provider_fault(
    tmp_path: Path,
) -> None:
    """The fetch validates the answer, so the rejection is a provider fault.

    Reported as a fault rather than as a Coverage Gap because the window was
    never answered for — the provider misbehaved.
    """
    provider = _ForeignRecordProvider(_foreign_record())

    with pytest.raises(GapFillProviderError, match="another instrument"):
        ingest(
            FixtureRecord,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-03"),
            provider=provider,
            catalog=Catalog.open(tmp_path),
        )


def test_a_foreign_provider_record_never_reaches_storage(tmp_path: Path) -> None:
    """Neither door into the Catalog admits a record for another instrument.

    Pinned because the storage command underneath the fill path is shared with
    live capture.
    """
    provider = _ForeignRecordProvider(_foreign_record())
    with pytest.raises(GapFillProviderError):
        ingest(
            FixtureRecord,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-03"),
            provider=provider,
            catalog=Catalog.open(tmp_path),
        )

    stored = records(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog=Catalog.open(tmp_path),
    )

    assert stored == ()


def _foreign_record() -> FixtureRecord:
    timestamp = _utc("2024-01-02").value
    return FixtureRecord(
        timestamp,
        timestamp,
        instrument_id=InstrumentId.from_str("QQQ.NASDAQ"),
        value=7.0,
        provider="fixture",
    )


def test_ingest_is_idempotent_and_records_round_trip_typed(tmp_path: Path) -> None:
    provider = _Provider((_record("2024-01-02", 7.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=provider,
        catalog=Catalog.open(tmp_path),
    )
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=provider,
        catalog=Catalog.open(tmp_path),
    )
    stored = records(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog=Catalog.open(tmp_path),
    )

    assert provider.requests == [(_utc("2024-01-01"), _utc("2024-01-03"))]
    assert stored == (_record("2024-01-02", 7.0),)
    assert isinstance(stored[0], FixtureRecord)


def test_records_for_arrays_resolves_kinds_and_returns_covered_records(
    tmp_path: Path,
) -> None:
    provider = _Provider((_record("2024-01-02", 7.0),))
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=provider,
        catalog=Catalog.open(tmp_path),
    )
    stored = records_for_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog=Catalog.open(tmp_path),
    )

    assert stored == (_record("2024-01-02", 7.0),)


def test_records_for_arrays_rejects_an_unknown_array_name(tmp_path: Path) -> None:
    with pytest.raises(UnknownCustomArrayError, match="UnknownFixtureValue"):
        records_for_arrays(
            {_INSTRUMENT: ("UnknownFixtureValue",)},
            start=_utc("2024-01-01"),
            end=_utc("2024-01-03"),
            catalog=Catalog.open(tmp_path),
        )


def test_ingest_translates_provider_failures_at_the_shared_coverage_boundary(
    tmp_path: Path,
) -> None:
    class _BrokenProvider(CustomDataProviderPort[FixtureRecord]):
        def request_records(
            self,
            instrument_id: InstrumentId,
            *,
            start: pd.Timestamp,
            end: pd.Timestamp,
        ) -> ProviderAnswer[FixtureRecord]:
            raise RuntimeError("vendor socket vanished")

    with pytest.raises(GapFillProviderError, match="custom data for SPY.ARCA"):
        ingest(
            FixtureRecord,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-03"),
            provider=_BrokenProvider(),
            catalog=Catalog.open(tmp_path),
        )


def test_ingest_never_persists_records_before_provider_served_from(
    tmp_path: Path,
) -> None:
    provider = _Provider(
        (_record("2024-01-02", 2.0),),
        oldest_verified=_utc("2024-01-05"),
    )

    with pytest.raises(CatalogCoverageGapError):
        ingest(
            FixtureRecord,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-06"),
            provider=provider,
            catalog=Catalog.open(tmp_path),
        )

    assert (
        records(
            FixtureRecord,
            (_INSTRUMENT,),
            start=_utc("2024-01-01"),
            end=_utc("2024-01-06"),
            catalog=Catalog.open(tmp_path),
        )
        == ()
    )


def test_ingest_fills_only_an_interior_native_gap(tmp_path: Path) -> None:
    seed = _Provider((_record("2024-01-02", 2.0), _record("2024-01-08", 8.0)))
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=seed,
        catalog=Catalog.open(tmp_path),
    )
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-07"),
        end=_utc("2024-01-10"),
        provider=seed,
        catalog=Catalog.open(tmp_path),
    )
    healer = _Provider((_record("2024-01-05", 5.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-10"),
        provider=healer,
        catalog=Catalog.open(tmp_path),
    )

    assert healer.requests == [
        (
            pd.Timestamp(_utc("2024-01-03").value + 1, tz="UTC"),
            pd.Timestamp(_utc("2024-01-07").value - 1, tz="UTC"),
        )
    ]


def test_ensure_arrays_heals_only_the_gap_between_live_records(
    tmp_path: Path,
) -> None:
    first = _record("2024-01-01", 2.0)
    last = _record("2024-01-03", 8.0)
    capture(first, catalog=Catalog.open(tmp_path))
    capture(last, catalog=Catalog.open(tmp_path))
    provider = _Provider(())

    ensure_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers={FixtureRecord: provider},
        catalog=Catalog.open(tmp_path),
    )
    assert provider.requests == [
        (
            pd.Timestamp("2024-01-01 00:00:00.000000001", tz="UTC"),
            pd.Timestamp("2024-01-02 23:59:59.999999999", tz="UTC"),
        )
    ]


def test_ensure_arrays_makes_no_request_for_a_fully_covered_window(
    tmp_path: Path,
) -> None:
    seed = _Provider(())
    ensure_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers={FixtureRecord: seed},
        catalog=Catalog.open(tmp_path),
    )
    unused = _Provider(())

    ensure_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers={FixtureRecord: unused},
        catalog=Catalog.open(tmp_path),
    )

    assert unused.requests == []


def test_marker_backed_gap_does_not_break_a_later_horizon_extension(
    tmp_path: Path,
) -> None:
    capture(_record("2024-01-01", 2.0), catalog=Catalog.open(tmp_path))
    capture(_record("2024-01-03", 8.0), catalog=Catalog.open(tmp_path))
    ensure_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        providers={FixtureRecord: _Provider(())},
        catalog=Catalog.open(tmp_path),
    )
    extension = _Provider((_record("2024-01-04", 9.0),))

    ensure_arrays(
        {_INSTRUMENT: ("FixtureValue", "FixtureAvailable")},
        start=_utc("2024-01-01"),
        end=_utc("2024-01-04"),
        providers={FixtureRecord: extension},
        catalog=Catalog.open(tmp_path),
    )

    assert extension.requests == [
        (
            pd.Timestamp("2024-01-03 00:00:00.000000001", tz="UTC"),
            _utc("2024-01-04"),
        )
    ]


def test_arrays_distinguishes_verified_empty_from_never_ingested(
    tmp_path: Path,
) -> None:
    empty = _Provider(())
    index = pd.date_range("2024-01-01", "2024-01-03", tz="UTC")
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=index[0],
        end=index[-1],
        provider=empty,
        catalog=Catalog.open(tmp_path),
    )

    panels = arrays(
        ("FixtureValue", "FixtureAvailable"),
        (_INSTRUMENT,),
        index=index,
        catalog=Catalog.open(tmp_path),
    )
    report = coverage(
        FixtureRecord,
        (_INSTRUMENT,),
        start=index[0],
        end=index[-1],
        catalog=Catalog.open(tmp_path),
    )

    assert panels["FixtureValue"].to_numpy().tolist() == [[0.0], [0.0], [0.0]]
    assert panels["FixtureAvailable"].to_numpy().tolist() == [[0.0], [0.0], [0.0]]
    assert report[0].instrument_id == _INSTRUMENT
    with pytest.raises(CatalogCoverageGapError):
        arrays(
            ("FixtureValue",),
            (_INSTRUMENT,),
            index=index,
            catalog=Catalog.open(tmp_path / "never-ingested"),
        )


def test_correction_replaces_a_bounded_window_while_ingest_cannot_overwrite(
    tmp_path: Path,
) -> None:
    original = _Provider((_record("2024-01-02", 2.0),))
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=original,
        catalog=Catalog.open(tmp_path),
    )
    correct(
        FixtureRecord,
        _INSTRUMENT,
        (_record("2024-01-02", 9.0),),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog=Catalog.open(tmp_path),
    )
    attempted_overwrite = _Provider((_record("2024-01-02", 3.0),))

    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        provider=attempted_overwrite,
        catalog=Catalog.open(tmp_path),
    )
    stored = records(
        FixtureRecord,
        (_INSTRUMENT,),
        start=_utc("2024-01-01"),
        end=_utc("2024-01-03"),
        catalog=Catalog.open(tmp_path),
    )

    assert attempted_overwrite.requests == []
    assert stored == (_record("2024-01-02", 9.0),)


def test_arrays_projects_fixture_records_causally_on_the_exact_index(
    tmp_path: Path,
) -> None:
    index = pd.date_range("2024-01-01", "2024-01-05", tz="UTC")
    provider = _Provider((_record("2024-01-02", 2.0), _record("2024-01-04", 4.0)))
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=index[0],
        end=index[-1],
        provider=provider,
        catalog=Catalog.open(tmp_path),
    )

    panels = arrays(
        ("FixtureValue", "FixtureAvailable", "FixtureAgeDays"),
        (_INSTRUMENT,),
        index=index,
        catalog=Catalog.open(tmp_path),
    )

    assert panels["FixtureValue"].index.equals(index)
    assert panels["FixtureValue"].columns.tolist() == [_INSTRUMENT]
    assert panels["FixtureValue"].to_numpy().tolist() == [
        [0.0],
        [2.0],
        [2.0],
        [4.0],
        [4.0],
    ]
    assert panels["FixtureAvailable"].to_numpy().tolist() == [
        [0.0],
        [1.0],
        [1.0],
        [1.0],
        [1.0],
    ]
    assert panels["FixtureAgeDays"].to_numpy().tolist() == [
        [0.0],
        [0.0],
        [1.0],
        [0.0],
        [1.0],
    ]
    assert not panels["FixtureValue"].isna().to_numpy().any()
    assert not panels["FixtureAvailable"].isna().to_numpy().any()
    assert not panels["FixtureAgeDays"].isna().to_numpy().any()


def test_arrays_carries_the_latest_record_from_before_the_requested_index(
    tmp_path: Path,
) -> None:
    coverage_index = pd.date_range("2024-01-01", "2024-01-05", tz="UTC")
    provider = _Provider((_record("2024-01-01", 2.0),))
    ingest(
        FixtureRecord,
        (_INSTRUMENT,),
        start=coverage_index[0],
        end=coverage_index[-1],
        provider=provider,
        catalog=Catalog.open(tmp_path),
    )
    requested_index = coverage_index[2:]

    panels = arrays(
        ("FixtureValue", "FixtureAvailable", "FixtureAgeDays"),
        (_INSTRUMENT,),
        index=requested_index,
        catalog=Catalog.open(tmp_path),
    )

    assert panels["FixtureValue"].to_numpy().tolist() == [[2.0], [2.0], [2.0]]
    assert panels["FixtureAvailable"].to_numpy().tolist() == [[1.0], [1.0], [1.0]]
    assert panels["FixtureAgeDays"].to_numpy().tolist() == [[2.0], [3.0], [4.0]]


def test_arrays_accepts_names_spanning_multiple_custom_kinds(
    tmp_path: Path,
) -> None:
    index = pd.DatetimeIndex([], tz="UTC")

    panels = arrays(
        ("FixtureValue", "DormantFixtureValue"),
        (_INSTRUMENT,),
        index=index,
        catalog=Catalog.open(tmp_path),
    )

    assert tuple(panels) == ("FixtureValue", "DormantFixtureValue")
    assert panels["FixtureValue"].index.equals(index)
    assert panels["DormantFixtureValue"].columns.tolist() == [_INSTRUMENT]


def test_vocabulary_contains_only_provisioned_fixture_arrays() -> None:
    vocabulary = FIXTURE_CUSTOM_DATA_KINDS.vocabulary

    assert vocabulary == frozenset(
        {"FixtureValue", "FixtureAvailable", "FixtureAgeDays"}
    )


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
