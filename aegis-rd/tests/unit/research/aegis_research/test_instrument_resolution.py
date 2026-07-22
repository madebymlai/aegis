from __future__ import annotations

from datetime import date

from aegis_data.catalog import ResolvedContinuousRoot
from aegis_data.roll import DatedContract
from aegis_runtime import DriftBand
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import TypeAdapter

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.configuration import (
    DataConfig,
    InstrumentBandConfig,
    PortfolioConfig,
)
from research.aegis_research.instrument_resolution import (
    InstrumentResolution,
    TradeableInstrument,
    resolve_instruments,
)

_DATA = TypeAdapter(DataConfig)
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")


class _CatalogPort:
    def resolve_continuous(self, root: str) -> ResolvedContinuousRoot:
        if root != "ES":
            raise AssertionError(f"unexpected continuous root {root!r}")
        return ResolvedContinuousRoot(
            _ES,
            (DatedContract("ESH4.XCME", date(2024, 3, 15)),),
        )


def test_resolution_preserves_ordered_structural_tradeable_identity() -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES"],
            "timeframe": "1D",
        }
    )

    resolution = resolve_instruments(data, port=_CatalogPort())

    assert resolution == InstrumentResolution(
        tradeables=(
            TradeableInstrument(instrument_id=_AAPL),
            TradeableInstrument(instrument_id=_ES, continuous_root="ES"),
        )
    )
    assert to_builtin(resolution.tradeables) == [
        {"instrument_id": "AAPL.NASDAQ", "continuous_root": None},
        {"instrument_id": "ES.XCME", "continuous_root": "ES"},
    ]


def test_resolution_projects_one_exact_drift_band_key_per_tradeable() -> None:
    resolution = InstrumentResolution(
        tradeables=(
            TradeableInstrument(instrument_id=_AAPL),
            TradeableInstrument(instrument_id=_ES, continuous_root="ES"),
        )
    )
    portfolio = PortfolioConfig(
        direction="both",
        band_up=0.10,
        band_down=0.20,
        band_overrides={
            "AAPL.NASDAQ": InstrumentBandConfig(up=0.01, down=0.03),
            "ES": InstrumentBandConfig(up=0.05, down=0.08),
        },
    )

    bands = resolution.instrument_bands(portfolio)

    assert bands == {
        _AAPL: DriftBand(0.01, 0.03),
        _ES: DriftBand(0.05, 0.08),
    }
