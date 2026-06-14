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
