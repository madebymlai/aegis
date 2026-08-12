from pathlib import Path

import pandas as pd

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import CoverageInterval
from aegis_data.distributions import Distribution
from aegis_data.storage import Catalog, CatalogKey
from tests.test_catalog import _id


def test_deleting_an_interior_coverage_range_rematerializes_both_residuals(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    subject = CatalogKey.for_instrument(Distribution, _id("SPY.ARCA"))
    markers = CoverageMarkerLedger(catalog)
    full = _interval("2024-01-01", "2024-01-05")
    removed = _interval("2024-01-03", "2024-01-03")

    markers.mark(
        subject,
        full,
        checked_at_ns=_ns("2026-01-01"),
        applicable=True,
    )
    markers.delete(subject, removed)

    assert markers.missing(subject, full) == [removed]


def test_filename_repair_does_not_change_residual_coverage_claims(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    subject = CatalogKey.for_instrument(Distribution, _id("SPY.ARCA"))
    markers = CoverageMarkerLedger(catalog)
    full = _interval("2024-01-01", "2024-01-05")
    removed = _interval("2024-01-03", "2024-01-03")

    markers.mark(
        subject,
        full,
        checked_at_ns=_ns("2026-01-01"),
        applicable=True,
    )
    markers.delete(subject, removed)
    markers.repair_interval_descriptions(subject)

    assert markers.missing(subject, full) == [removed]


def test_provenance_for_a_strict_subwindow_reads_the_overlapping_claim(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    subject = CatalogKey.for_instrument(Distribution, _id("SPY.ARCA"))
    markers = CoverageMarkerLedger(catalog)
    checked_at_ns = _ns("2026-01-01")

    markers.mark(
        subject,
        _interval("2024-01-01", "2024-01-05"),
        checked_at_ns=checked_at_ns,
        applicable=True,
    )

    assert markers.checked_at_values(
        subject, _interval("2024-01-02", "2024-01-04")
    ) == [checked_at_ns, checked_at_ns]


def _interval(start: str, end: str) -> CoverageInterval:
    return CoverageInterval(_ns(start), _ns(end))


def _ns(value: str) -> int:
    return pd.Timestamp(value, tz="UTC").value
