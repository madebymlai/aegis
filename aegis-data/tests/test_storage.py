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
    friday, saturday, monday = (
        _day("2024-01-05"),
        _day("2024-01-06"),
        _day("2024-01-08"),
    )
    sunday_end = _day("2024-01-07").end_ns

    weekend = CatalogInterval(saturday.start_ns, sunday_end)

    catalog.replace(key, friday, (_bar(bar_type, friday.start_ns),))
    catalog.replace(key, monday, (_bar(bar_type, monday.start_ns),))
    catalog.replace(key, weekend, ())
    # Rewriting Monday clears the window first — the path that used to erase it.
    catalog.replace(key, monday, (_bar(bar_type, monday.start_ns),))

    assert catalog.missing(key, weekend) == ()


def test_replacing_a_window_with_no_records_still_records_it_as_checked(
    tmp_path: Path,
) -> None:
    """An empty answer is an answer: the window was asked, and held nothing.

    Nautilus records that by extending the neighbouring file's name over the
    range, which is what its own data engine reads to decide whether to fetch.
    Returning early on empty records leaves no trace, so the window is asked
    again on every startup.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    bar_type = BarType.from_str("SPY.ARCA-1-DAY-LAST-EXTERNAL")
    key = CatalogKey.for_bar(bar_type)
    friday, saturday = _day("2024-01-05"), _day("2024-01-06")

    catalog.replace(key, friday, (_bar(bar_type, friday.start_ns),))
    catalog.replace(key, saturday, ())

    assert catalog.missing(key, saturday) == ()


def test_dropping_an_interior_range_leaves_both_catalog_extents(
    tmp_path: Path,
) -> None:
    """Removing the middle of a Catalog extent must preserve its outer files.

    The vendor splits a partially overlapping file rather than discarding it,
    so the surviving names still describe the days either side. Only the
    dropped range goes back to being unanswered.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    full = CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-05", tz="UTC").value,
    )
    middle = CatalogInterval(
        pd.Timestamp("2024-01-03", tz="UTC").value,
        pd.Timestamp("2024-01-03", tz="UTC").value,
    )

    catalog.replace(
        key,
        full,
        (
            Distribution.from_ex_date(_SPY, "2024-01-01", amount=0.10, currency="USD"),
            Distribution.from_ex_date(_SPY, "2024-01-05", amount=0.50, currency="USD"),
        ),
    )
    catalog.drop(key, middle)

    assert catalog.missing(key, full) == (middle,)


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
    stale = Distribution.from_ex_date(_SPY, "2024-01-02", amount=0.25, currency="USD")
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
    stale = Distribution.from_ex_date(_SPY, "2024-01-02", amount=0.25, currency="USD")

    catalog.replace(key, interval, (stale,))
    catalog.replace(key, interval, ())

    assert catalog.read(key, interval) == ()


def test_compaction_preserves_the_coverage_of_the_windows_it_merges(
    tmp_path: Path,
) -> None:
    """Merging a run of answered windows must not change what is answered.

    The survivor is named for the span of the files it replaces, so a run of
    adjacent windows — including one that was checked and held nothing —
    compacts to exactly the same coverage it started with.
    """
    catalog = Catalog.open(tmp_path / "catalog")
    bar_type = BarType.from_str("SPY.ARCA-1-DAY-LAST-EXTERNAL")
    key = CatalogKey.for_bar(bar_type)
    friday, saturday, monday = (
        _day("2024-01-05"),
        _day("2024-01-06"),
        _day("2024-01-08"),
    )
    sunday = _day("2024-01-07")
    weekend = CatalogInterval(saturday.start_ns, sunday.end_ns)
    span = CatalogInterval(friday.start_ns, monday.end_ns)

    catalog.replace(key, friday, (_bar(bar_type, friday.start_ns),))
    catalog.replace(key, weekend, ())
    catalog.replace(key, monday, (_bar(bar_type, monday.start_ns),))
    before = catalog.missing(key, span)
    catalog.compact(key, span)

    assert before == ()
    assert catalog.missing(key, span) == ()
    assert len(catalog.read(key, span)) == 2


_CONTIGUITY_PROBE = """
import sys

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.storage import Catalog, CatalogInterval, CatalogKey

assert_enabled = False
try:
    assert False
except AssertionError:
    assert_enabled = True

BAR_TYPE = BarType.from_str("SPY.ARCA-1-DAY-LAST-EXTERNAL")


def day(value):
    start = pd.Timestamp(value, tz="UTC")
    return CatalogInterval(start.value, (start + pd.Timedelta(days=1)).value - 1)


def bar(at):
    price = Price.from_str("470.00")
    return Bar(BAR_TYPE, price, price, price, price, Quantity.from_str("1"), at, at)


catalog = Catalog.open(sys.argv[1])
key = CatalogKey.for_bar(BAR_TYPE)
friday, monday = day("2024-01-05"), day("2024-01-08")
weekend = CatalogInterval(day("2024-01-06").start_ns, day("2024-01-07").end_ns)
span = CatalogInterval(friday.start_ns, monday.end_ns)

# Written the way every writer here writes: each window abuts the last.
catalog.replace(key, friday, (bar(friday.start_ns),))
catalog.replace(key, weekend, ())
catalog.replace(key, monday, (bar(monday.start_ns),))
catalog.compact(key, span)

print(f"{assert_enabled}:{catalog.missing(key, span) == ()}")
"""


def test_compaction_holds_its_coverage_even_with_assertions_disabled(
    tmp_path: Path,
) -> None:
    """The writers, not the vendor's guard, are what make compaction safe.

    ``ensure_contiguous_files`` is an ``assert``, so ``python -O`` strips it.
    That is tolerable only because every window written here abuts the last,
    leaving compaction no hole to stretch a filename over. Run both ways: the
    coverage answer must not depend on which one the process happens to use.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(_CONTIGUITY_PROBE)

    verdicts = {
        flags: subprocess.run(
            [
                sys.executable,
                *flags,
                str(probe),
                str(tmp_path / f"catalog{len(flags)}"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for flags in ((), ("-O",))
    }

    assert verdicts[()] == "True:True"
    assert verdicts[("-O",)] == "False:True"
