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

from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.run_data import RunData


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
        portfolio: PortfolioConfig,
        run_data: RunData,
    ) -> ResolvedBook:
        """Resolve every per-instrument fact from one complete RunData value.

        A leg is non-base by its currency *derived from the resolved Instrument*
        (the conversion's ``currency_by_instrument_id``), never a configured field.
        The structural resolution carries native and continuous tradeables together,
        so fee, band, root, and size facts cannot describe different universes.
        """
        resolution = run_data.instrument_resolution
        instrument_ids = resolution.instrument_ids
        return cls(
            config=portfolio,
            fees_by_symbol=_fx_adjusted_fees(
                instrument_ids,
                run_data.currency_conversion.currency_by_instrument_id,
                portfolio.base_currency,
                base_fee=portfolio.fees,
                fx_conversion_cost=portfolio.fx_conversion_cost,
            ),
            instrument_bands=resolution.instrument_bands(portfolio),
            futures_roots=tuple(
                tradeable.continuous_root
                for tradeable in resolution.tradeables
                if tradeable.continuous_root is not None
            ),
            size_increment_by_instrument=run_data.size_increment_by_instrument,
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
