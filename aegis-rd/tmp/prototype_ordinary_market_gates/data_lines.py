"""PROTOTYPE (throwaway) — data access for the gate measurements.

Warm catalog reads (never connects to IBKR) plus two public HTTP fetches
cached in `.cache/` beside this file.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

CATALOG_ROOT = Path.home() / ".local/share/aegis-data/catalog"
CACHE = Path(__file__).parent / ".cache"

DIX_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
BCOM_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBCOM?range=35y&interval=1d"


def catalog_close(bar_type: str) -> pd.Series:
    """Daily close of a catalog bar line, indexed by trading date."""
    from nautilus_trader.persistence.catalog import ParquetDataCatalog

    bars = ParquetDataCatalog(CATALOG_ROOT).bars(bar_types=[bar_type])
    idx = pd.DatetimeIndex([pd.Timestamp(b.ts_event).normalize() for b in bars])
    return pd.Series([float(b.close) for b in bars], index=idx, name=bar_type)


def _fetch(url: str, cache_name: str) -> bytes:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / cache_name
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    return path.read_bytes()


def squeezemetrics_frame() -> pd.DataFrame:
    """Columns: price (SPX close), dix, gex; indexed by US trading date."""
    from io import BytesIO

    df = pd.read_csv(BytesIO(_fetch(DIX_URL, "DIX.csv")), parse_dates=["date"])
    return df.set_index("date").sort_index()


def bcom_index_close() -> pd.Series:
    """^BCOM daily close from the Yahoo chart API."""
    j = json.loads(_fetch(BCOM_URL, "bcom.json"))
    r = j["chart"]["result"][0]
    ts = r["timestamp"]
    close = r["indicators"]["quote"][0]["close"]
    pairs = [(t, c) for t, c in zip(ts, close) if c is not None]
    idx = pd.DatetimeIndex(
        [pd.Timestamp(t, unit="s", tz="UTC").tz_convert(None).normalize() for t, _ in pairs]
    )
    s = pd.Series([c for _, c in pairs], index=idx, name="^BCOM")
    return s[~s.index.duplicated(keep="last")]
