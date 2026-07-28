from __future__ import annotations

from aegis_runtime import DriftBand

from research.aegis_research.configuration import InstrumentBandConfig, PortfolioConfig


def test_base_currency_defaults_to_eur_and_is_overridable() -> None:
    default = PortfolioConfig(direction="both")
    assert default.base_currency == "EUR"

    chosen = PortfolioConfig(direction="both", base_currency="GBP")
    assert chosen.base_currency == "GBP"


def test_fx_conversion_cost_defaults_off() -> None:
    cfg = PortfolioConfig(direction="both")
    assert cfg.fx_conversion_cost == 0.0

    priced = PortfolioConfig(direction="both", fx_conversion_cost=0.0003)
    assert priced.fx_conversion_cost == 0.0003


def test_resolved_band_for_falls_back_to_sleeve_default_when_no_override() -> None:
    cfg = PortfolioConfig(direction="both", band_up=0.10, band_down=0.20)
    assert cfg.resolved_band_for("AAPL.NASDAQ") == DriftBand(up=0.10, down=0.20)


def test_resolved_band_for_prefers_exact_key_over_sleeve_default() -> None:
    cfg = PortfolioConfig(
        direction="both",
        band_up=0.10,
        band_down=0.20,
        band_overrides={"AAPL.NASDAQ": InstrumentBandConfig(up=0.01, down=0.03)},
    )
    assert cfg.resolved_band_for("AAPL.NASDAQ") == DriftBand(up=0.01, down=0.03)


def test_resolved_band_for_carries_the_sleeve_destination_fraction() -> None:
    cfg = PortfolioConfig(
        direction="both",
        band_up=0.10,
        band_down=0.20,
        band_destination_fraction=0.5,
    )
    assert cfg.resolved_band_for("AAPL.NASDAQ") == DriftBand(
        up=0.10, down=0.20, destination_fraction=0.5
    )


def test_override_without_destination_fraction_inherits_the_sleeve_default() -> None:
    cfg = PortfolioConfig(
        direction="both",
        band_up=0.10,
        band_down=0.20,
        band_destination_fraction=0.5,
        band_overrides={
            "AAPL.NASDAQ": InstrumentBandConfig(up=0.01, down=0.03),
            "ES": InstrumentBandConfig(up=0.05, down=0.08, destination_fraction=1.0),
        },
    )
    assert cfg.resolved_band_for("AAPL.NASDAQ") == DriftBand(
        up=0.01, down=0.03, destination_fraction=0.5
    )
    assert cfg.resolved_band_for("ES") == DriftBand(up=0.05, down=0.08, destination_fraction=1.0)


def test_resolved_band_for_matches_the_override_key_exactly() -> None:
    cfg = PortfolioConfig(
        direction="both",
        band_up=0.10,
        band_down=0.20,
        band_overrides={"ES": InstrumentBandConfig(up=0.05, down=0.08)},
    )
    # The override is keyed by the bare root "ES"; the caller passes that one canonical
    # key. A different key (e.g. the resolved id) does not match — no silent fallback.
    assert cfg.resolved_band_for("ES") == DriftBand(up=0.05, down=0.08)
    assert cfg.resolved_band_for("ES.XCME") == DriftBand(up=0.10, down=0.20)
