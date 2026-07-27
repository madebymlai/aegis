"""Free VSTOXX daily history, from a checked-in snapshot of STOXX's own archive.

VSTOXX carries no Yahoo Finance ticker at all: Yahoo's own quote-search API returns zero
matches for "VSTOXX" (checked directly against ``query1.finance.yahoo.com``), and every
Yahoo ticker guessed from community references (``V2TX.DE``, ``^V2TX``, ``OVS.EX``,
``^VSTOXX``) comes back delisted/empty. The only free, no-signup source found is STOXX's
own historical-data file, and this module reads a fixed snapshot of it rather than
fetching it live. Two things carry forward into every verdict built on this:

1. This module used to fetch ``h_vstoxx.txt`` from ``www.stoxx.com`` on every run, with TLS
   verification disabled — that host serves this file with an incomplete certificate chain
   (the identical "unable to get local issuer certificate" failure was independently
   reproduced against two unrelated HTTP clients, so this is STOXX's server
   misconfiguration, not a local trust-store problem). That bypass has been removed: it
   asked every future caller of this prototype to inherit an unverified connection, and the
   file it was fetching has not changed since 2016-02-12 (point 2), so a live fetch had no
   ongoing value anyway. ``fixtures/h_vstoxx.txt`` is a byte-for-byte copy of the response
   fetched on 2026-07-25, checked in below with its sha256 recorded in
   ``FIXTURE_SHA256`` — anyone can re-fetch ``ORIGIN_URL`` themselves and diff or hash it
   against this file to confirm it has not been altered.
2. The file is frozen at 2016-02-12 — STOXX appears to have retired this free
   distribution mechanism some time after that date in favour of a subscriber-only quotes
   API (``quotes.stoxx.com``, confirmed to return 401 Unauthorized without an API key).
   Whatever this test finds can only speak to the years immediately around and after the
   August-2012 break; it is silent on 2016-2026, the most decision-relevant stretch.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd

ORIGIN_URL = (
    "https://www.stoxx.com/document/Indices/Current/HistoricalData/h_vstoxx.txt"
)
FETCHED_ON = "2026-07-25"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "h_vstoxx.txt"
FIXTURE_SHA256 = "4b4076135a5f5817794c5f8cb44858e2475a7ac81b198f1a43e4174bd961b76b"
VSTOXX_COLUMN = "V2TX"

Fetch = Callable[[], str]


class VstoxxHistoryError(ValueError):
    """The STOXX historical-data file does not match the schema this parser expects."""


class FixtureIntegrityError(ValueError):
    """The bundled fixture no longer matches the sha256 recorded alongside it."""


@dataclass(frozen=True)
class VstoxxHistory:
    level: pd.Series
    source_url: str
    start: str
    end: str
    observations: int


def _verify_and_decode(raw: bytes) -> str:
    """Check ``raw`` against the recorded checksum before trusting it as the fixture."""
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FIXTURE_SHA256:
        raise FixtureIntegrityError(
            f"{FIXTURE_PATH} does not match the recorded sha256 {FIXTURE_SHA256} "
            f"(got {digest}). This file should never change; re-fetch {ORIGIN_URL} "
            "yourself and compare before trusting it, or update FIXTURE_SHA256 only if "
            "this is a deliberate, re-verified refresh."
        )
    return raw.decode("utf-8")


def _read_fixture() -> str:
    return _verify_and_decode(FIXTURE_PATH.read_bytes())


def load_vstoxx_history(fetch: Fetch = _read_fixture) -> VstoxxHistory:
    """Parse and validate the complete free VSTOXX (V2TX) daily history."""
    level = _parse(fetch())[VSTOXX_COLUMN]
    if not level.between(3.0, 150.0).all():
        raise VstoxxHistoryError("VSTOXX values fall outside a plausible 3-150 range")
    return VstoxxHistory(
        level=level,
        source_url=ORIGIN_URL,
        start=level.index[0].date().isoformat(),
        end=level.index[-1].date().isoformat(),
        observations=len(level),
    )


def _parse(text: str) -> pd.DataFrame:
    lines = text.splitlines()
    if len(lines) < 4 or not lines[2].startswith("Date,"):
        raise VstoxxHistoryError(
            "unexpected header shape in the STOXX historical-data file"
        )
    header = lines[2].split(",")
    if VSTOXX_COLUMN not in header:
        raise VstoxxHistoryError(f"missing expected column {VSTOXX_COLUMN!r}")
    frame = pd.read_csv(StringIO("\n".join(lines[3:])), names=header, na_values=["NA"])
    frame["Date"] = pd.to_datetime(frame["Date"], format="%d.%m.%Y")
    frame = frame.set_index("Date").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.dropna(subset=[VSTOXX_COLUMN])
    if frame.empty:
        raise VstoxxHistoryError("parsed history has no usable VSTOXX observations")
    if not frame.index.is_monotonic_increasing:
        raise VstoxxHistoryError("parsed history is not chronologically ordered")
    return frame
