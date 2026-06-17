"""OS-global parquet store for historical market data.

Per-contract pulls are cached as parquet under the OS user-data directory
(``platformdirs``), overridable with ``AEGIS_DATA_DIR``.  A repeated identical
request reads the parquet instead of re-hitting the provider — this is the
"``source:`` omitted means the cache path" default, shared by Aegis RD and Aegis
Trader (both read the same store).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import platformdirs

from aegis_data.chain import ContractFetcher

_APP = "aegis-data"


def data_dir() -> Path:
    """The historical-data store root: ``$AEGIS_DATA_DIR`` or the OS user-data dir."""
    override = os.environ.get("AEGIS_DATA_DIR")
    return Path(override) if override else Path(platformdirs.user_data_dir(_APP))


def futures_dir(dataset: str, *, store_dir: Path | None = None) -> Path:
    return (store_dir or data_dir()) / "futures" / dataset


def cached_fetcher(
    fetch: ContractFetcher, *, dataset: str, store_dir: Path | None = None
) -> ContractFetcher:
    """Wrap a per-contract fetcher with a write-through parquet cache in the store.

    Keyed by ``(symbol, start, end)``; on a miss it fetches and writes, then
    always returns the parquet-materialised frame (cache-hit and miss agree).
    """
    root = futures_dir(dataset, store_dir=store_dir)

    def cached(symbol: str, start: date, end: date) -> pd.DataFrame:
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{symbol}_{start.isoformat()}_{end.isoformat()}.parquet"
        if not path.exists():
            fetch(symbol, start, end).to_parquet(path)
        return pd.read_parquet(path)

    return cached


__all__ = ["cached_fetcher", "data_dir", "futures_dir"]
