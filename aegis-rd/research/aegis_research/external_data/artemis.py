"""Content-addressed snapshots of Artemis cat-bond market carry data."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

SOURCE_URL = "https://www.artemis.bm/catastrophe-bond-market-yield/"
SERIES = ("Collateral Yield", "Insurance Risk Spread", "Expected Loss")


class ArtemisParseError(ValueError):
    """The public Artemis page no longer matches the expected schema."""


class ArtemisIntegrityError(ValueError):
    """A pinned snapshot's observations do not match its identity."""


@dataclass(frozen=True)
class ArtemisSnapshot:
    frame: pd.DataFrame
    source_url: str
    source_sha256: str
    retrieved_at: str


def parse_market_yield_page(html: str) -> pd.DataFrame:
    """Parse and validate the three aligned public Highcharts series."""
    category_match = re.search(r"categories:\s*\[(.*?)\],\s*labels", html, re.DOTALL)
    if category_match is None:
        raise ArtemisParseError("Artemis page has no market-yield categories")
    dates = ast.literal_eval(f"[{category_match.group(1)}]")
    matches = re.findall(r"name:\s*'([^']+)'.*?data:\s*\[(.*?)\]", html, re.DOTALL)
    values = {
        name: ast.literal_eval(f"[{raw}]") for name, raw in matches if name in SERIES
    }
    if tuple(name for name in SERIES if name not in values):
        raise ArtemisParseError("Artemis page is missing a required market-yield series")
    if any(len(values[name]) != len(dates) for name in SERIES):
        raise ArtemisParseError("Artemis market-yield dates and series are not aligned")
    index = pd.to_datetime(dates, format="%d/%m/%Y")
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ArtemisParseError("Artemis market-yield dates must be unique and increasing")
    frame = pd.DataFrame({name: values[name] for name in SERIES}, index=index, dtype=float)
    if not (frame >= -0.1).all().all():
        raise ArtemisParseError("Artemis market-yield series contains implausible values")
    return frame


def snapshot_payload(html: str, *, retrieved_at: datetime | None = None) -> dict:
    """Return the stable snapshot document for downloaded HTML."""
    frame = parse_market_yield_page(html)
    stamp = (retrieved_at or datetime.now(UTC)).isoformat()
    observations = [
        {"date": date.date().isoformat(), **{name: row[name] for name in SERIES}}
        for date, row in frame.iterrows()
    ]
    snapshot_hash = hashlib.sha256(
        json.dumps(observations, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "source_url": SOURCE_URL,
        "source_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "snapshot_sha256": snapshot_hash,
        "retrieved_at": stamp,
        "observations": observations,
    }


def refresh_snapshot(destination: Path) -> Path:
    """Fetch once and write an immutable content-addressed snapshot."""
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    payload = snapshot_payload(response.text)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"cat_bond_market_yield-{payload['snapshot_sha256'][:16]}.json"
    if not path.exists():
        path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load_snapshot(path: Path) -> ArtemisSnapshot:
    """Load a pinned snapshot and validate its stored observations."""
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise ArtemisIntegrityError("unsupported Artemis snapshot schema")
    actual_hash = hashlib.sha256(
        json.dumps(payload["observations"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual_hash != payload.get("snapshot_sha256") or actual_hash[:16] not in path.name:
        raise ArtemisIntegrityError("Artemis snapshot content does not match its identity")
    frame = pd.DataFrame(payload["observations"]).set_index("date")
    frame.index = pd.to_datetime(frame.index)
    frame = frame.loc[:, list(SERIES)].astype(float)
    if frame.empty or not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ArtemisIntegrityError("invalid Artemis snapshot observations")
    return ArtemisSnapshot(
        frame=frame,
        source_url=payload["source_url"],
        source_sha256=payload["source_sha256"],
        retrieved_at=payload["retrieved_at"],
    )
