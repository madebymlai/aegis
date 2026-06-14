from __future__ import annotations

from research.aegis_research.configuration import PortfolioConfig


def test_base_currency_defaults_to_eur_and_is_overridable() -> None:
    default = PortfolioConfig(gross_cap=1.0, direction="both")
    assert default.base_currency == "EUR"

    chosen = PortfolioConfig(gross_cap=1.0, direction="both", base_currency="GBP")
    assert chosen.base_currency == "GBP"


def test_fx_conversion_cost_defaults_off() -> None:
    cfg = PortfolioConfig(gross_cap=1.0, direction="both")
    assert cfg.fx_conversion_cost == 0.0

    priced = PortfolioConfig(gross_cap=1.0, direction="both", fx_conversion_cost=0.0003)
    assert priced.fx_conversion_cost == 0.0003
