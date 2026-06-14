"""Source adapters behind the unchanged MarketDataAdapter seam."""

from __future__ import annotations

from research.aegis_research.market_data.adapters.csv import load_csv_source
from research.aegis_research.market_data.adapters.remote import (
    remote_source_loaders,
)
from research.aegis_research.market_data.adapters.synthetic import (
    load_synthetic_source,
)
from research.aegis_research.market_data.contracts import MarketDataAdapter


def default_source_loaders() -> dict[str, MarketDataAdapter]:
    return {
        "synthetic": load_synthetic_source,
        "csv": load_csv_source,
        **remote_source_loaders(),
    }


__all__ = [
    "default_source_loaders",
    "load_csv_source",
    "load_synthetic_source",
    "remote_source_loaders",
]
