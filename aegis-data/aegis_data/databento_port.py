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
from datetime import date, timedelta
from typing import Any

import pandas as pd

from aegis_data.chain import ContractCalendar, ContractFetcher
from aegis_data.roll import DatedContract

# databento publisher venue for the GLBX.MDP3 dataset (CME Globex).
_GLBX_VENUE = "GLBX"


def databento_contract_calendar(dataset: str, *, client: Any | None = None) -> ContractCalendar:
    """List a root's outright dated futures (``raw_symbol`` + expiration) from Databento
    definitions, via parent symbology (``{ROOT}.FUT``).

    These supply the expiry-driven roll, so a monthly product lists its monthly contracts
    and a serial/odd-cycle product lists whatever it actually trades — no hardcoded cycle.
    ``client`` is injectable for tests; production constructs a Databento historical client
    from ``DATABENTO_API_KEY``.
    """

    def list_contracts(root: str, start: date, end: date) -> list[DatedContract]:
        api = client if client is not None else _databento_historical_client()
        store = api.timeseries.get_range(
            dataset=dataset,
            schema="definition",
            symbols=[f"{root}.FUT"],
            stype_in="parent",
            start=str(start),
            end=str(end + timedelta(days=1)),  # end-exclusive guard
        )
        frame = store.to_df()
        if frame.empty:
            return []
        outright = frame[frame["instrument_class"] == "F"].drop_duplicates("raw_symbol")
        return [
            DatedContract(str(row["raw_symbol"]), pd.Timestamp(row["expiration"]).date())
            for _, row in outright.iterrows()
        ]

    return list_contracts


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
        start_ns = pd.Timestamp(start).value
        end_ns = (pd.Timestamp(end) + pd.Timedelta(days=1)).value  # end-exclusive guard
        bars = asyncio.run(_pull(api, dataset, instrument_id, start_ns, end_ns))
        return bars_to_ohlcv(bars)

    return fetch


async def _pull(api: Any, dataset: str, instrument_id: Any, start_ns: int, end_ns: int) -> list[Any]:
    from nautilus_trader.core.nautilus_pyo3 import BarAggregation

    # Load definitions first so the port resolves price precision itself.
    await api.get_range_instruments(dataset, [instrument_id], start_ns, end_ns)
    return await api.get_range_bars(
        dataset, [instrument_id], BarAggregation.DAY, start_ns, end_ns, timestamp_on_close=False
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


__all__ = ["bars_to_ohlcv", "databento_contract_calendar", "databento_port_fetcher"]
