"""Unit tests for BookConfig — zero Nautilus."""

import pytest

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName


def make_sleeve(name: str, wheel: str = "test.whl", budget: float = 1.0) -> SleeveConfig:
    return SleeveConfig(name=SleeveName(name), wheel_filename=wheel, budget=budget)


class TestBookConfig:
    def test_single_sleeve_defaults(self):
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.sleeve_count == 1
        assert book.base_currency == "EUR"
        assert book.sleeves[0].name == SleeveName("trend")
        assert book.sleeves[0].budget == 1.0

    def test_duplicate_sleeve_names_rejected(self):
        with pytest.raises(ValueError, match="duplicate"):
            BookConfig(sleeves=(make_sleeve("a"), make_sleeve("a")))

    def test_empty_sleeves_rejected(self):
        with pytest.raises(ValueError, match="at least one sleeve"):
            BookConfig(sleeves=())

    def test_custom_base_currency(self):
        book = BookConfig(sleeves=(make_sleeve("trend"),), base_currency="USD")
        assert book.base_currency == "USD"

    def test_book_gross_at_default_max_allowed(self):
        """Σ budgets == 1.0 (fully invested, no leverage) is allowed by default."""
        book = BookConfig(sleeves=(make_sleeve("a", budget=0.6), make_sleeve("b", budget=0.4)))
        assert book.sleeve_count == 2

    def test_book_gross_above_default_max_rejected(self):
        """Σ budgets > 1.0 is leverage and must be opted into via max_book_gross."""
        with pytest.raises(ValueError, match="book gross"):
            BookConfig(sleeves=(make_sleeve("a", budget=0.7), make_sleeve("b", budget=0.7)))

    def test_book_gross_leverage_allowed_when_max_raised(self):
        book = BookConfig(
            sleeves=(make_sleeve("a", budget=1.0), make_sleeve("b", budget=1.0)),
            max_book_gross=2.0,
        )
        assert book.sleeve_count == 2


class TestBookConfigCapsAndBands:
    """Caps and bands declaration.

    Cap *provenance* (caps never exceeding the bundles' research-validated
    ceilings) is bundle-grounded and lives in test_cap_provenance.py — it is no
    longer a self-referential check on BookConfig.
    """

    def test_default_bands(self):
        """Default bands are 0.02 symmetric."""
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.band_for("ANY_FIGI") == (0.02, 0.02)

    def test_band_override(self):
        """Per-FIGI asymmetric band override."""
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            band_overrides=(("FIGI_TAIL", 0.01, 0.05),),
        )
        assert book.band_for("FIGI_TAIL") == (0.01, 0.05)
        assert book.band_for("OTHER") == (0.02, 0.02)

    def test_caps_default_none(self):
        """Caps default to None (unlimited)."""
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.gross_cap is None
        assert book.net_cap is None
        assert book.per_name_cap is None
        assert book.aggregate_drift_threshold is None

    def test_custom_caps(self):
        """All caps can be set."""
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            gross_cap=1.5,
            net_cap=0.8,
            per_name_cap=0.15,
            aggregate_drift_threshold=0.05,
        )
        assert book.gross_cap == 1.5
        assert book.net_cap == 0.8
        assert book.per_name_cap == 0.15
        assert book.aggregate_drift_threshold == 0.05
