"""Per-contract fetch via the NautilusTrader databento port.

Uses Nautilus's cached historical client (``get_cached_databento_http_client``)
— the Nautilus-owned databento port, not the raw SDK — to pull one dated
contract's daily bars and normalise them to a canonical OHLCV DataFrame on a
naive date index.  Instrument definitions are loaded first so the port resolves
price precision itself (no per-product hardcoding).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd

from aegis_data.chain import ContractCalendar, ContractFetcher
from aegis_data.roll import DatedContract

# A long sequential pull (dozens of roots × years of dated contracts) makes a single transient
# provider hiccup — a 5xx gateway timeout or a dropped connection — fatal unless absorbed.
_FETCH_ATTEMPTS = 4
_TRANSIENT_MARKERS = (
    "502", "503", "504", "gateway", "timeout", "timed out", "connection reset", "connection aborted",
)

# databento publisher venue for the GLBX.MDP3 dataset (CME Globex).
_GLBX_VENUE = "GLBX"

# When a window outruns the listed forward curve and nothing at all is listed at an anchor
# (a brand-new or dormant root), step ahead by this much before snapshotting again.
_UNLISTED_STEP = timedelta(days=180)

# The per-leg definitions snapshot (for static price precision) is loaded over a short window
# ending at the bars' late edge rather than a single day: a contract's definition is dropped
# from the active set on its last-trade day when it stopped trading earlier (last bar < last
# trade), so a single day at exactly the edge can land on the delisted day and fail to resolve
# precision.  A bounded lookback straddles the still-active days without scaling with the window.
_DEFS_LOOKBACK = timedelta(days=14)


def databento_contract_calendar(dataset: str, *, client: Any | None = None) -> ContractCalendar:
    """List a root's outright dated futures (``raw_symbol`` + expiration) from Databento
    definitions, via parent symbology (``{ROOT}.FUT``).

    These supply the expiry-driven roll, so a monthly product lists its monthly contracts
    and a serial/odd-cycle product lists whatever it actually trades — no hardcoded cycle.

    A single definition snapshot returns *all* instruments active that day, and CME lists the
    whole forward curve years out, so one snapshot near ``start`` usually already enumerates
    every contract expiring in the window.  Coverage is read back from each snapshot (its
    furthest expiration): only when the window outruns the listed curve — a multi-decade
    backtest beyond the listing horizon — does the calendar resample at the frontier to pick
    up contracts that list later.  Anchors are nudged onto a weekday (definitions snapshot
    Mon–Fri).  ``client`` is injectable for tests; production constructs a Databento
    historical client from ``DATABENTO_API_KEY``.
    """

    def list_contracts(root: str, start: date, end: date) -> list[DatedContract]:
        api = client if client is not None else _databento_historical_client()
        contracts: dict[date, str] = {}  # expiration -> chosen raw_symbol (one contract per expiry)
        anchor = start
        while anchor <= end:
            snapshot_day = _to_weekday(anchor)
            _collect_outrights(_definition_snapshot(api, dataset, root, snapshot_day), contracts)
            covered = max(contracts, default=None)
            if covered is not None and covered >= end:
                break  # the listed forward curve already spans the window
            anchor = (
                max(covered, snapshot_day) + timedelta(days=1)
                if covered is not None
                else snapshot_day + _UNLISTED_STEP
            )
        return [DatedContract(symbol, expiry) for expiry, symbol in sorted(contracts.items())]

    return list_contracts


def _is_transient_provider_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def retrying_fetcher(
    fetch: ContractFetcher,
    *,
    attempts: int = _FETCH_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> ContractFetcher:
    """Wrap a per-contract fetcher so transient provider errors (5xx / gateway timeout /
    dropped connection) retry with exponential backoff.

    A single flaky response must not abort a multi-hour sequential pull; a non-transient error
    (bad symbol, auth) still fails fast so it surfaces immediately.
    """

    def fetch_with_retry(symbol: str, start: date, end: date) -> pd.DataFrame:
        for attempt in range(1, attempts + 1):
            try:
                return fetch(symbol, start, end)
            except Exception as error:  # noqa: BLE001 — provider errors are not a typed hierarchy
                if attempt == attempts or not _is_transient_provider_error(error):
                    raise
                sleep(min(2.0**attempt, 30.0))
        raise AssertionError("unreachable")  # pragma: no cover

    return fetch_with_retry


def _to_weekday(day: date) -> date:
    """Nudge a weekend anchor onto the next weekday (definitions snapshot Mon–Fri)."""
    while day.weekday() >= 5:  # Saturday (5) or Sunday (6)
        day += timedelta(days=1)
    return day


def _collect_outrights(frame: pd.DataFrame, into: dict[date, str]) -> None:
    """Merge a snapshot's outright futures into ``into``, keyed by expiration so each
    delivery month maps to a single contract — the one a desk actually trades.

    Spreads (instrument_class ``S``) are dropped.  A subtler duplicate is ICE-specific:
    each delivery month is listed under both its *base outright* (switch character ``!`` —
    "no additional data", ICE Instrument Naming Convention §1.8.1) and auxiliary derived
    markets that share the same expiration and that Databento *also* classes ``F`` — notably
    the Trade-at-Settlement book (``_Z``, §1.8.5.4), which carries a fraction of the volume.
    Keying by ``raw_symbol`` admitted both, so one expiry produced two ``DatedContract``s and
    chain assembly aborted at the seam (aegis-rd-min).  Keying by expiration and preferring
    the ``!`` base outright collapses each month to that future.  CME (GLBX) lists one symbol
    per expiry with no ``!`` switch, so the preference never fires and first-seen wins.
    """
    if frame.empty:
        return
    outright = frame[frame["instrument_class"] == "F"]
    for _, row in outright.iterrows():
        expiry = pd.Timestamp(row["expiration"]).date()
        symbol = str(row["raw_symbol"])
        incumbent = into.get(expiry)
        if incumbent is None or (_is_base_outright(symbol) and not _is_base_outright(incumbent)):
            into[expiry] = symbol


def _is_base_outright(symbol: str) -> bool:
    """True for an ICE *base* outright — switch character ``!`` ("no additional data", ICE
    Instrument Naming Convention §1.8.1).  Auxiliary ICE markets that share a future's
    expiration (Trade-at-Settlement ``_Z`` and other underscore blocks) end otherwise.  CME
    symbols carry no switch character, so this is simply ``False`` for them — and never
    competes, since CME lists one outright per expiry."""
    return symbol.endswith("!")


def _definition_snapshot(api: Any, dataset: str, root: str, day: date) -> pd.DataFrame:
    store = api.timeseries.get_range(
        dataset=dataset,
        schema="definition",
        symbols=[f"{root}.FUT"],
        stype_in="parent",
        start=str(day),
        end=str(day + timedelta(days=1)),  # one 24h-from-midnight snapshot
    )
    return store.to_df()


def _databento_historical_client() -> Any:
    import databento

    return databento.Historical(os.environ["DATABENTO_API_KEY"])


def databento_port_fetcher(
    dataset: str,
    *,
    venue: str = _GLBX_VENUE,
    client: Any | None = None,
) -> ContractFetcher:
    """A per-contract fetcher backed by the Nautilus databento port.

    ``client`` is injectable for tests; in production it is Nautilus's cached
    historical client (reads ``DATABENTO_API_KEY`` from the environment).
    """

    def fetch(symbol: str, start: date, end: date) -> pd.DataFrame:
        api = client if client is not None else _nautilus_databento_client()
        instrument_id = _instrument_id(f"{symbol}.{venue}")
        bars_start_ns = pd.Timestamp(start).value
        bars_end_ns = (pd.Timestamp(end) + pd.Timedelta(days=1)).value  # end-exclusive guard
        # Price precision is static, so definitions load over a short window — not the whole bars
        # span.  Anchor that window at the bars' LATE edge with a lookback, not a single day.  Two
        # failure modes bracket the anchor: a contract is only listed a bounded horizon before
        # expiry, so a snapshot at the window start (years before, when the liquidity probe spans
        # the whole panel) cannot resolve a far-dated contract (Databento 422); yet its definition
        # is also dropped from the active set on its last-trade day when it stopped trading earlier
        # (last bar < last trade), so a single day at exactly the late edge can land on the
        # delisted day and fail to resolve precision.  A lookback window ending at the late edge
        # straddles both — inside the listed life, spanning days the definition is still active —
        # while staying bounded so the load never scales with the bars window.
        defs_start_ns = (pd.Timestamp(end) - _DEFS_LOOKBACK).value
        defs_end_ns = (pd.Timestamp(end) + pd.Timedelta(days=1)).value
        bars = asyncio.run(
            _pull(api, dataset, instrument_id, defs_start_ns, defs_end_ns, bars_start_ns, bars_end_ns)
        )
        return bars_to_ohlcv(bars)

    # Transient 5xx/timeout responses are absorbed with backoff so one flaky leg does not
    # abort the whole pull; the leg cache means a retried success is still fetched only once.
    return retrying_fetcher(fetch)


async def _pull(
    api: Any,
    dataset: str,
    instrument_id: Any,
    defs_start_ns: int,
    defs_end_ns: int,
    bars_start_ns: int,
    bars_end_ns: int,
) -> list[Any]:
    from nautilus_trader.core.nautilus_pyo3 import BarAggregation

    # Load definitions first so the port resolves price precision itself.
    await api.get_range_instruments(dataset, [instrument_id], defs_start_ns, defs_end_ns)
    return await api.get_range_bars(
        dataset, [instrument_id], BarAggregation.DAY, bars_start_ns, bars_end_ns, timestamp_on_close=False
    )


def bars_to_ohlcv(bars: list[Any]) -> pd.DataFrame:
    """Convert Nautilus pyo3 ``Bar``s to an OHLCV DataFrame on a naive date index."""
    index: list[pd.Timestamp] = []
    rows: dict[str, list[float]] = {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []}
    for bar in bars:
        index.append(pd.Timestamp(bar.ts_event).normalize())
        rows["Open"].append(float(bar.open.as_double()))
        rows["High"].append(float(bar.high.as_double()))
        rows["Low"].append(float(bar.low.as_double()))
        rows["Close"].append(float(bar.close.as_double()))
        rows["Volume"].append(float(bar.volume.as_double()))
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex(index))
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def _nautilus_databento_client() -> Any:
    from nautilus_trader.adapters.databento import get_cached_databento_http_client

    return get_cached_databento_http_client()


def _instrument_id(value: str) -> Any:
    from nautilus_trader.core.nautilus_pyo3 import InstrumentId

    return InstrumentId.from_str(value)


__all__ = [
    "bars_to_ohlcv",
    "databento_contract_calendar",
    "databento_port_fetcher",
    "retrying_fetcher",
]
