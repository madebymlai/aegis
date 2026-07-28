"""Distribution coverage behavior through the catalog port boundary."""

from pathlib import Path

import pytest
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    CatalogWindowRequest,
    raw_bar_type,
)
from tests.test_catalog import (
    _bar,
    _fx_mid_resolver,
    _id,
    _seed_fx_pair,
    _write_definition,
    _write_span,
)


def test_missing_distribution_provider_fails_before_writing_other_markers(
    tmp_path: Path,
) -> None:
    catalog = ParquetDataCatalog(tmp_path / "catalog")
    fx_pair = _id("EUR/USD.IDEALPRO")
    equity = _id("SPY.ARCA")
    _seed_fx_pair(catalog, fx_pair)
    _write_definition(catalog, equity)
    equity_bars = raw_bar_type(equity, "1D")
    _write_span(
        catalog,
        [
            _bar(equity_bars, "2024-01-01", 100.0),
            _bar(equity_bars, "2024-01-02", 100.0),
            _bar(equity_bars, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    port = CatalogBackedDataPort(catalog, resolver=_fx_mid_resolver(fx_pair))
    request = CatalogWindowRequest(
        (fx_pair, equity),
        start="2024-01-01",
        end="2024-01-04",
    )

    with pytest.raises(CatalogCoverageGapError, match="SPY.ARCA"):
        port.load_window(request)
    report = port.distribution_coverage_report(
        (fx_pair,),
        start=request.start,
        end=request.end,
    )

    assert report[0]["checked_at"] is None
