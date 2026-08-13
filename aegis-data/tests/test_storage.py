import subprocess
import sys
from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.distributions import Distribution
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


_SPY = InstrumentId.from_str("SPY.ARCA")


def test_replacing_a_window_keeps_the_checked_empty_window_beside_it(
    tmp_path: Path,
) -> None:
    """Writing must not erase a window Nautilus recorded as checked and empty.

    Nautilus records "asked, and there was nothing" by extending an adjacent
    file's name over the empty range — that name is what its own data engine
    reads to decide whether to fetch. ``delete_data_range`` maintains those
    names itself; rebuilding them from file contents, which nothing here needs,
    erases the record and makes the engine re-request the window on every
    startup.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    bar_type = BarType.from_str("SPY.ARCA-1-DAY-LAST-EXTERNAL")
    key = CatalogKey.for_bar(bar_type)
    friday, saturday, monday = _day("2024-01-05"), _day("2024-01-06"), _day("2024-01-08")
    sunday_end = _day("2024-01-07").end_ns

    catalog.replace(key, friday, (_bar(bar_type, friday.start_ns),))
    catalog.replace(key, monday, (_bar(bar_type, monday.start_ns),))
    # As the data engine does when a request comes back empty.
    catalog._store.write_data(
        [],
        saturday.start_ns,
        sunday_end,
        data_cls=Bar,
        identifier=str(bar_type),
    )
    # Rewriting Monday clears the window first — the path that used to erase it.
    catalog.replace(key, monday, (_bar(bar_type, monday.start_ns),))

    weekend_as_the_engine_sees_it = catalog._store.get_missing_intervals_for_request(
        saturday.start_ns,
        sunday_end,
        Bar,
        str(bar_type),
    )

    assert weekend_as_the_engine_sees_it == []


def _day(date: str) -> CatalogInterval:
    start = pd.Timestamp(date, tz="UTC")
    return CatalogInterval(start.value, (start + pd.Timedelta(days=1)).value - 1)


def _bar(bar_type: BarType, at: int) -> Bar:
    return Bar(
        bar_type,
        Price.from_str("470.00"),
        Price.from_str("471.00"),
        Price.from_str("469.00"),
        Price.from_str("470.50"),
        Quantity.from_str("100"),
        at,
        at,
    )


def test_replace_window_overwrites_stale_rows_and_is_idempotent(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    interval = CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-03", tz="UTC").value,
    )
    stale = Distribution.from_ex_date(
        _SPY, "2024-01-02", amount=0.25, currency="USD"
    )
    corrected = Distribution.from_ex_date(
        _SPY, "2024-01-02", amount=0.50, currency="USD"
    )

    catalog.replace(key, interval, (stale,))
    catalog.replace(key, interval, (corrected,))
    catalog.replace(key, interval, (corrected,))
    stored = catalog.read(key, interval)

    assert stored == (corrected,)


def test_a_dropped_window_can_be_written_again(
    tmp_path: Path,
) -> None:
    """Dropping the middle of a stored window leaves that window writable.

    The surviving files describe what they actually hold, so a later write into
    the hole does not collide with a stale description of a record that is no
    longer there.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    jan_1 = pd.Timestamp("2024-01-01", tz="UTC").value
    jan_3 = pd.Timestamp("2024-01-03", tz="UTC").value
    jan_5 = pd.Timestamp("2024-01-05", tz="UTC").value
    stored = (
        Distribution.from_ex_date(_SPY, "2024-01-01", amount=0.10, currency="USD"),
        Distribution.from_ex_date(_SPY, "2024-01-02", amount=0.20, currency="USD"),
        Distribution.from_ex_date(_SPY, "2024-01-03", amount=0.30, currency="USD"),
        Distribution.from_ex_date(_SPY, "2024-01-04", amount=0.40, currency="USD"),
        Distribution.from_ex_date(_SPY, "2024-01-05", amount=0.50, currency="USD"),
    )
    full = CatalogInterval(jan_1, jan_5)

    catalog.replace(key, full, stored)
    catalog.drop(key, CatalogInterval(jan_3, jan_3))

    assert catalog.read(key, full) == (stored[0], stored[1], stored[3], stored[4])

    replacement = Distribution.from_ex_date(
        _SPY, "2024-01-03", amount=0.35, currency="USD"
    )
    catalog.replace(key, CatalogInterval(jan_3, jan_3), (replacement,))

    assert catalog.read(key, full) == (
        stored[0],
        stored[1],
        replacement,
        stored[3],
        stored[4],
    )


def test_bar_key_round_trips_without_exposing_its_serialized_identifier(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    bar_type = BarType.from_str("SPY.ARCA-1-DAY-LAST-EXTERNAL")
    key = CatalogKey.for_bar(bar_type)
    at = pd.Timestamp("2024-01-02", tz="UTC").value
    interval = CatalogInterval(at, at)
    bar = Bar(
        bar_type,
        Price.from_str("470.00"),
        Price.from_str("471.00"),
        Price.from_str("469.00"),
        Price.from_str("470.50"),
        Quantity.from_str("100"),
        at,
        at,
    )

    catalog.replace(key, interval, (bar,))
    stored = catalog.read(key, interval)

    assert stored == (bar,)


def test_replace_window_with_no_records_clears_stale_payload(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    interval = CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-03", tz="UTC").value,
    )
    stale = Distribution.from_ex_date(
        _SPY, "2024-01-02", amount=0.25, currency="USD"
    )

    catalog.replace(key, interval, (stale,))
    catalog.replace(key, interval, ())

    assert catalog.read(key, interval) == ()


def test_compaction_merges_across_a_hole_without_losing_a_record(
    tmp_path: Path,
) -> None:
    """File layout is free precisely because it carries no coverage meaning.

    Merging these two files widens what the surviving filename spans across a
    January gap. Nothing asks a filename what was checked — the coverage
    claims do that — so the only thing compaction must protect is the records.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    jan_1 = pd.Timestamp("2024-01-01", tz="UTC").value
    jan_2 = pd.Timestamp("2024-01-02", tz="UTC").value
    jan_4 = pd.Timestamp("2024-01-04", tz="UTC").value
    jan_5 = pd.Timestamp("2024-01-05", tz="UTC").value
    first = Distribution.from_ex_date(
        _SPY, "2024-01-01", amount=0.10, currency="USD"
    )
    second = Distribution.from_ex_date(
        _SPY, "2024-01-04", amount=0.40, currency="USD"
    )
    full = CatalogInterval(jan_1, jan_5)

    catalog.replace(key, CatalogInterval(jan_1, jan_2), (first,))
    catalog.replace(key, CatalogInterval(jan_4, jan_5), (second,))
    catalog.compact(key, full)

    assert catalog.read(key, full) == (first, second)


_HOLE_PROBE = """
import sys

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import CoverageInterval
from aegis_data.distributions import Distribution
from aegis_data.storage import Catalog, CatalogKey

assert_enabled = False
try:
    assert False
except AssertionError:
    assert_enabled = True


def day(value):
    return pd.Timestamp(value, tz="UTC").value


subject = CatalogKey.for_instrument(Distribution, InstrumentId.from_str("SPY.ARCA"))
ledger = CoverageMarkerLedger(Catalog.open(sys.argv[1]))
for checked in (("2024-01-01", "2024-01-31"), ("2024-03-01", "2024-03-31")):
    ledger.mark(
        subject,
        CoverageInterval(day(checked[0]), day(checked[1])),
        checked_at_ns=day("2024-04-01"),
        applicable=True,
    )

ledger.consolidate(subject, CoverageInterval(day("2024-01-01"), day("2024-03-31")))
february = CoverageInterval(day("2024-02-05"), day("2024-02-06"))
print(f"{assert_enabled}:{bool(ledger.missing(subject, february))}")
"""


def test_compaction_never_invents_coverage_even_with_assertions_disabled(
    tmp_path: Path,
) -> None:
    """Merging files must not merge claims.

    The vendor guards contiguous consolidation with ``assert``, which
    ``python -O`` strips. Coverage is read from the claims themselves rather
    than from file extents, so an unchecked February stays unchecked however
    the files are laid out — and with whatever flags the process runs under.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(_HOLE_PROBE)

    verdicts = {
        flags: subprocess.run(
            [sys.executable, *flags, str(probe), str(tmp_path / f"catalog{len(flags)}")],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for flags in ((), ("-O",))
    }

    assert verdicts[()] == "True:True"
    assert verdicts[("-O",)] == "False:True"
