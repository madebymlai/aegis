"""The catalog loader package — the implementation behind the load entry point."""

from __future__ import annotations

from research.aegis_research.market_data.adapters.catalog import load_catalog_source

__all__ = [
    "load_catalog_source",
]
