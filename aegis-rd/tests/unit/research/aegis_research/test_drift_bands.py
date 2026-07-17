from __future__ import annotations

from aegis_runtime import DriftBand
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import InstrumentBandConfig, PortfolioConfig
from research.aegis_research.drift_bands import instrument_bands_from

_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")


def _portfolio(**kwargs: object) -> PortfolioConfig:
    return PortfolioConfig(direction="both", **kwargs)  # type: ignore[arg-type]


def test_instrument_bands_from_fans_sleeve_default_to_every_instrument() -> None:
    bands = instrument_bands_from(
        ((_AAPL, None), (_ES, "ES")),
        _portfolio(band_up=0.10, band_down=0.20),
    )

    assert bands == {_AAPL: DriftBand(0.10, 0.20), _ES: DriftBand(0.10, 0.20)}


def test_instrument_bands_from_applies_native_and_root_overrides() -> None:
    bands = instrument_bands_from(
        ((_AAPL, None), (_ES, "ES")),
        _portfolio(
            band_up=0.10,
            band_down=0.20,
            band_overrides={
                "AAPL.NASDAQ": InstrumentBandConfig(up=0.01, down=0.03),
                "ES": InstrumentBandConfig(up=0.05, down=0.08),
            },
        ),
    )

    # The native is keyed by its full id; the future's override is keyed by the bare
    # root "ES" yet resolves onto the continuous id "ES.XCME" — one canonical key each.
    assert bands[_AAPL] == DriftBand(0.01, 0.03)
    assert bands[_ES] == DriftBand(0.05, 0.08)
