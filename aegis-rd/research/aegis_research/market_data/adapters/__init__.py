"""Source adapters behind the unchanged MarketDataAdapter seam."""

from __future__ import annotations

from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.contracts import MarketDataAdapter


def default_source_loaders() -> dict[str, MarketDataAdapter]:
    return {"catalog": load_catalog_source}


__all__ = [
    "default_source_loaders",
    "load_catalog_source",
]
