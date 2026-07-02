"""Resolve a run's per-instrument no-trade drift bands — the single authority.

Both the execution-bundle export and the research simulation resolve bands here, so
the band the backtest gates on is the band the bundle carries. Each tradeable resolves
to one canonical override key (a continuous future's bare ``data.futures`` root, a
native's full InstrumentId) and an exact lookup against ``band_overrides`` — no
try-this-then-that fallback. An unset override falls to the sleeve-wide default.
"""

from __future__ import annotations

from collections.abc import Iterable

from aegis_runtime import DriftBand, InstrumentId

from research.aegis_research.configuration import PortfolioConfig, RunConfig
from research.aegis_research.market_data.identity import resolved_instruments


def resolve_instrument_bands(config: RunConfig) -> dict[InstrumentId, DriftBand]:
    """The complete instrument → :class:`DriftBand` map for a run config.

    Resolves the run's tradeable universe (natives + continuous-future roots) and
    fans the sleeve default plus per-instrument overrides across it.
    """
    return instrument_bands_from(resolved_instruments(config), config.portfolio)


def instrument_bands_from(
    resolved: Iterable[tuple[InstrumentId, str | None]],
    portfolio: PortfolioConfig,
) -> dict[InstrumentId, DriftBand]:
    """Map each resolved instrument to its drift band, keyed by its full InstrumentId.

    *resolved* pairs each tradeable's full id with its bare ``data.futures`` root (or
    ``None`` for a native). The override key is that one canonical token, so resolution
    is a single exact lookup per instrument.
    """
    return {
        instrument_id: portfolio.resolved_band_for(
            root if root is not None else instrument_id.value
        )
        for instrument_id, root in resolved
    }
