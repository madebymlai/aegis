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
        assert book.default_venue == "XLON"
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

    def test_custom_venue(self):
        book = BookConfig(sleeves=(make_sleeve("trend"),), default_venue="XETR")
        assert book.default_venue == "XETR"


class TestBookConfigSlice4:
    """Slice 4: caps, bands, provenance assertion."""

    def test_per_name_cap_exceeding_research_cap_rejected(self):
        """BookConfig per_name_cap > sleeve research_validated_cap → ValueError."""
        with pytest.raises(ValueError, match="per_name_cap.*exceeds"):
            BookConfig(
                sleeves=(SleeveConfig(
                    name=SleeveName("trend"),
                    wheel_filename="trend.whl",
                    budget=1.0,
                    research_validated_cap=0.15,
                ),),
                per_name_cap=0.20,
            )

    def test_per_name_cap_within_research_cap_allowed(self):
        """BookConfig per_name_cap ≤ research_validated_cap is fine."""
        book = BookConfig(
            sleeves=(SleeveConfig(
                name=SleeveName("trend"),
                wheel_filename="trend.whl",
                budget=1.0,
                research_validated_cap=0.15,
            ),),
            per_name_cap=0.12,
        )
        assert book.per_name_cap == 0.12

    def test_per_name_cap_ok_when_no_research_cap(self):
        """No research_validated_cap on sleeves → no provenance check."""
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            per_name_cap=0.20,
        )
        assert book.per_name_cap == 0.20

    def test_multiple_sleeves_all_must_pass_provenance(self):
        """Every sleeve with a research cap must be ≥ per_name_cap."""
        with pytest.raises(ValueError, match="per_name_cap.*exceeds"):
            BookConfig(
                sleeves=(
                    SleeveConfig(name=SleeveName("a"), wheel_filename="a.whl", budget=0.5,
                                 research_validated_cap=0.15),
                    SleeveConfig(name=SleeveName("b"), wheel_filename="b.whl", budget=0.5,
                                 research_validated_cap=0.10),
                ),
                per_name_cap=0.12,  # OK for a but exceeds b's 0.10
            )

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
