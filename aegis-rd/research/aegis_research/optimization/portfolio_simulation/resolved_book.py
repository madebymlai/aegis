"""The ResolvedBook a Run simulates under — declared policy plus resolved facts.

:class:`ResolvedBook` is the run-constant value the portfolio simulation trades
every Candidate's book under: the declared :class:`PortfolioConfig` together
with the per-instrument facts resolved from it — the FX-adjusted trade-fee
series, the instrument → :class:`DriftBand` map (the same one the bundle
carries), and the continuous-future roots. :meth:`ResolvedBook.resolve` owns
all three resolutions, so an incoherent config/facts pairing cannot exist as a
value; it is not the book of positions (that is the simulated portfolio).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd
from aegis_runtime import DriftBand, InstrumentId
from aegis_runtime.currency import CurrencyConversion

from research.aegis_research.configuration import PortfolioConfig, RunConfig
from research.aegis_research.drift_bands import resolve_instrument_bands


@dataclass(frozen=True)
class ResolvedBook:
    """The run-constant terms one simulated book trades under.

    ``fees_by_symbol`` of ``None`` keeps the scalar-fee path — byte-identical to
    a single-currency book — and ``instrument_bands`` of ``None`` gates every
    instrument at the sleeve-wide default; both stay meaningful for direct
    construction at the simulation seam. :meth:`resolve` always derives the
    real facts.
    """

    config: PortfolioConfig
    # Per-symbol trade fees (FX-conversion surcharge on non-base legs).
    fees_by_symbol: pd.Series | None = None
    # Resolved instrument → DriftBand map (the same one the bundle carries).
    instrument_bands: Mapping[InstrumentId, DriftBand] | None = None
    futures_roots: tuple[str, ...] = ()
    size_increment_by_instrument: Mapping[InstrumentId, float] | None = None

    @classmethod
    def resolve(
        cls,
        config: RunConfig,
        currency_conversion: CurrencyConversion | None,
        size_increment_by_instrument: Mapping[InstrumentId, float] | None = None,
    ) -> ResolvedBook:
        """Resolve the book's per-instrument facts from the declared config.

        A leg is non-base by its currency *derived from the resolved Instrument*
        (the conversion's ``currency_by_instrument_id``), never a configured
        field; a single-currency book has no conversion, so every leg reads as
        base and gets the uniform no-op fee series — no branch, no special case.
        """
        portfolio = config.portfolio
        instrument_ids = tuple(InstrumentId.from_str(value) for value in config.data.instruments)
        currency_by_instrument_id = (
            currency_conversion.currency_by_instrument_id
            if currency_conversion is not None
            else dict.fromkeys(instrument_ids, portfolio.base_currency)
        )
        return cls(
            config=portfolio,
            fees_by_symbol=_fx_adjusted_fees(
                instrument_ids,
                currency_by_instrument_id,
                portfolio.base_currency,
                base_fee=portfolio.fees,
                fx_conversion_cost=portfolio.fx_conversion_cost,
            ),
            instrument_bands=resolve_instrument_bands(config),
            futures_roots=tuple(config.data.futures),
            size_increment_by_instrument=size_increment_by_instrument,
        )


def _fx_adjusted_fees(
    instrument_ids: Sequence[InstrumentId],
    currency_by_instrument_id: Mapping[InstrumentId, str],
    base_currency: str,
    base_fee: float,
    fx_conversion_cost: float,
) -> pd.Series:
    """Per-instrument trade fee, adding the FX conversion cost to foreign legs.

    A foreign leg (one whose currency is not the book's base) crosses an FX
    spread on every trade - the EUR->ccy buy and the ccy->EUR sell - so it pays
    ``base_fee + fx_conversion_cost``; a base-currency leg pays ``base_fee``.
    """
    fees = {
        instrument_id: base_fee
        + (
            fx_conversion_cost
            if _requires_conversion(currency_by_instrument_id[instrument_id], base_currency)
            else 0.0
        )
        for instrument_id in instrument_ids
    }
    return pd.Series(fees)


def _requires_conversion(quote_currency: str, base_currency: str) -> bool:
    return quote_currency.upper() != base_currency.upper()
