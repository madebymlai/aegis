from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.distributions import Distribution
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


_SPY = InstrumentId.from_str("SPY.ARCA")


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


def test_drop_window_repairs_the_surviving_interval_descriptions(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    key = CatalogKey.for_instrument(Distribution, _SPY)
    jan_1 = pd.Timestamp("2024-01-01", tz="UTC").value
    jan_2 = pd.Timestamp("2024-01-02", tz="UTC").value
    jan_3 = pd.Timestamp("2024-01-03", tz="UTC").value
    jan_4 = pd.Timestamp("2024-01-04", tz="UTC").value
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
    assert catalog.missing(key, full) == (
        CatalogInterval(jan_2 + 1, jan_4 - 1),
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


def test_bounded_compaction_leaves_a_historical_hole_visible(tmp_path: Path) -> None:
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
    gap = (CatalogInterval(jan_2 + 1, jan_4 - 1),)

    catalog.replace(key, CatalogInterval(jan_1, jan_2), (first,))
    catalog.replace(key, CatalogInterval(jan_4, jan_5), (second,))
    catalog.compact(key, full)

    assert catalog.missing(key, full) == gap
    assert catalog.read(key, full) == (first, second)
