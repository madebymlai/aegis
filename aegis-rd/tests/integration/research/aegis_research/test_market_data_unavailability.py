"""The unavailability failure contract, end to end through the port seam.

A Run whose market data cannot be served — a coverage gap after backfill, or a
broken fetch — produces a judged ``data_unavailable`` verdict and
failure-shaped Evidence instead of an unhandled stack trace.  These tests
drive the full load → observe → judge → describe sequence through
``load_market_data_result(port=...)`` with the real ``CatalogBackedDataPort``
over fake catalogs (the port itself is never faked), exactly as production
wires it.  Authoring errors keep crashing loudly.
"""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_data.catalog import CatalogBackedDataPort, CatalogCoverageGapError
from aegis_data.testing import FakeCatalog, bars
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity, Instrument
from nautilus_trader.model.objects import Currency, Price, Quantity

from research.aegis_research.configuration import DataConfig
from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import (
    QUALITY_DATA_UNAVAILABLE,
    MarketDataUnavailableError,
)
from tests.support.research.aegis_research.factories import make_data_config
from tests.support.research.aegis_research.market_data_fixtures import (
    UnservableCatalog,
)

_AAPL = InstrumentId.from_str("AAPL.XNAS")


def _equity(instrument_id: InstrumentId) -> Instrument:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _frame(days: list[str], close: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(day) for day in days])
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [100.0] * len(close),
        },
        index=index,
    )


class _BrokenProvider:
    """A Gap-Fill Provider whose fetch faults environmentally (gateway drop)."""

    def request_bars(self, bar_type: BarType, **_kwargs: object) -> object:
        raise RuntimeError("gateway dropped mid-fetch")


def _config() -> DataConfig:
    return make_data_config(
        arrays=["Close"],
        base_currency="USD",
        instruments=[_AAPL.value],
        start="2024-01-01",
        end="2024-01-03",
    )


def test_coverage_gap_collapses_to_a_data_unavailable_verdict() -> None:
    port = CatalogBackedDataPort(UnservableCatalog(instruments=[_equity(_AAPL)], bars={}))

    result = load_market_data_result(_config(), port=port)

    assert result.quality.state == QUALITY_DATA_UNAVAILABLE
    assert not result.quality.usable
    assert result.native_data is None
    # The verdict carries the gate's exact judgement, not a generic phrase.
    assert "missing=" in result.quality.reasons[0]
    provenance = result.metadata.provenance
    assert provenance.source_metadata["error_type"] == "MarketDataUnavailableError"
    assert "missing=" in provenance.source_metadata["error_summary"]
    assert provenance.index_evidence["source"] == QUALITY_DATA_UNAVAILABLE
    assert len(result.metadata.diagnostics) == 1
    assert result.metadata.diagnostics[0].load_status == QUALITY_DATA_UNAVAILABLE


def test_broken_fetch_collapses_to_the_same_data_unavailable_verdict() -> None:
    port = CatalogBackedDataPort(
        UnservableCatalog(instruments=[_equity(_AAPL)], bars={}),
        provider=_BrokenProvider(),
    )

    result = load_market_data_result(_config(), port=port)

    assert result.quality.state == QUALITY_DATA_UNAVAILABLE
    assert not result.quality.usable
    assert "gateway dropped mid-fetch" in result.quality.reasons[0]


def test_authoring_errors_keep_propagating_uncaught() -> None:
    port = CatalogBackedDataPort(UnservableCatalog(instruments=[], bars={}))

    with pytest.raises(ValueError, match="start is required"):
        load_market_data_result(make_data_config(start=None), port=port)


class _QuietCatalog(FakeCatalog):
    """FakeCatalog plus the write/interval surface the distribution-coverage
    service touches; writes are dropped (coverage re-verifies per read)."""

    def get_intervals(self, *_args: object, **_kwargs: object) -> list:
        return []

    def write_data(self, *_args: object, **_kwargs: object) -> None:
        return None


class _NoDistributionProvider:
    """Adjusted-last equals TRADES closes: a verified window with zero events."""

    def __init__(self, closes: pd.Series) -> None:
        self._closes = closes

    def request_adjusted_last(self, **_kwargs: object) -> pd.Series:
        return self._closes


def test_the_port_passthrough_drives_the_production_wiring() -> None:
    """A warm catalog through ``port=`` loads healthy market data — the same
    wiring production uses, so tests and callers cross one seam."""
    frame = _frame(["2024-01-01", "2024-01-02", "2024-01-03"], [10.0, 11.0, 12.0])
    catalog = _QuietCatalog(
        instruments=[_equity(_AAPL)],
        bars={"AAPL.XNAS-1-DAY-LAST-EXTERNAL": bars(_AAPL, frame)},
    )
    closes = pd.Series(
        [10.0, 11.0, 12.0],
        index=pd.DatetimeIndex(
            [pd.Timestamp(day, tz="UTC") for day in frame.index], name="date"
        ),
    )
    port = CatalogBackedDataPort(
        catalog, distribution_provider=_NoDistributionProvider(closes)
    )

    result = load_market_data_result(_config(), port=port)

    assert result.quality.state == "healthy"
    assert result.metadata.coverage.rows == 3
    assert result.distributions == ()


def test_the_loader_wraps_only_port_environmental_errors() -> None:
    """The triage boundary: the catalog loader converts the port's environmental
    errors into the RD unavailability error; nothing else is disguised."""
    port = CatalogBackedDataPort(UnservableCatalog(instruments=[_equity(_AAPL)], bars={}))

    with pytest.raises(MarketDataUnavailableError) as excinfo:
        load_catalog_source(_config(), port=port)

    assert isinstance(excinfo.value.__cause__, CatalogCoverageGapError)
