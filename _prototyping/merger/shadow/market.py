"""Causal market marks loaded through Aegis's standard catalog-backed IBKR path."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from .ledger import EventObservation, EventStatus
from .selection import MarketMark


@dataclass(frozen=True)
class MarketUnavailable:
    """One pending event the market source could not value without guessing."""

    event_id: str
    ticker: str
    reason: str


@dataclass(frozen=True)
class MarketMarkBatch:
    """Available causal marks plus explicit exclusions."""

    marks: tuple[MarketMark, ...]
    unavailable: tuple[MarketUnavailable, ...]


class CatalogWindowPort(Protocol):
    def load_window(self, request: Any) -> Any: ...


class AegisCatalogMarkSource:
    """Derive frozen-q70 inputs from the shared catalog, filling gaps through IBKR."""

    def __init__(
        self,
        annual_cash_rate: float,
        *,
        catalog_path: Path | None = None,
        market_instrument_id: str = "SPY.ARCA",
        port: CatalogWindowPort | None = None,
    ) -> None:
        self._annual_cash_rate = annual_cash_rate
        self._catalog_path = catalog_path
        self._market_instrument_id = market_instrument_id
        self._port = port

    def load(
        self,
        events: Iterable[EventObservation],
        *,
        as_of: datetime,
    ) -> MarketMarkBatch:
        pending = tuple(
            event
            for event in events
            if event.status in {EventStatus.ANNOUNCED, EventStatus.AMENDED}
        )
        if not pending:
            return MarketMarkBatch((), ())

        ids = {
            event.event_id: InstrumentId.from_str(event.instrument_id) for event in pending
        }
        market_id = InstrumentId.from_str(self._market_instrument_id)
        earliest = min(datetime.fromisoformat(event.observed_at) for event in pending)
        start = (earliest - timedelta(days=100)).date().isoformat()
        end = as_of.date().isoformat()
        port = self._port or _catalog_port(self._catalog_path)
        frames = _window_frames(
            port,
            tuple(dict.fromkeys((*ids.values(), market_id))),
            start=start,
            end=end,
        )
        market = frames[market_id]
        marks: list[MarketMark] = []
        unavailable: list[MarketUnavailable] = []
        for event in pending:
            mark, reason = _mark(
                event,
                frames[ids[event.event_id]],
                market,
                as_of=as_of,
                annual_cash_rate=self._annual_cash_rate,
            )
            if mark is not None:
                marks.append(mark)
            if reason is not None:
                unavailable.append(MarketUnavailable(event.event_id, event.ticker, reason))
        return MarketMarkBatch(
            marks=tuple(sorted(marks, key=lambda item: item.ticker)),
            unavailable=tuple(sorted(unavailable, key=lambda item: (item.event_id, item.reason))),
        )


def _mark(
    event: EventObservation,
    target: pd.DataFrame,
    market: pd.DataFrame,
    *,
    as_of: datetime,
    annual_cash_rate: float,
) -> tuple[MarketMark | None, str | None]:
    announced = pd.Timestamp(datetime.fromisoformat(event.observed_at)).tz_localize(None)
    cutoff = pd.Timestamp(as_of).tz_localize(None)
    target = target.loc[target.index <= cutoff]
    market = market.loc[market.index <= cutoff]
    before_target = target.loc[target.index < announced]
    before_market = market.loc[market.index < announced]
    if target.empty or market.empty or before_target.empty or before_market.empty:
        return None, "missing current or pre-announcement bars"
    joined = pd.concat(
        [before_target["Close"].rename("target"), before_market["Close"].rename("market")],
        axis=1,
        join="inner",
    ).dropna()
    returns = np.log(joined).diff().dropna().tail(60)
    if len(returns) < 20:
        return None, "fewer than 20 pre-announcement beta returns"
    market_variance = float(returns["market"].var(ddof=1))
    if not math.isfinite(market_variance) or market_variance <= 0.0:
        return None, "pre-announcement market variance is not positive"
    beta = float(returns["target"].cov(returns["market"]) / market_variance)
    liquidity = (target["Close"] * target["Volume"]).tail(20).median()
    if not math.isfinite(float(liquidity)):
        return None, "median dollar volume is unavailable"
    observed = target.index[-1].tz_localize("UTC").isoformat()
    return (
        MarketMark(
            instrument_id=event.instrument_id,
            ticker=event.ticker,
            observed_at=observed,
            close=float(target["Close"].iloc[-1]),
            preannouncement_close=float(before_target["Close"].iloc[-1]),
            market_close=float(market["Close"].iloc[-1]),
            announcement_market_close=float(before_market["Close"].iloc[-1]),
            beta=beta,
            median_dollar_volume=float(liquidity),
            annual_cash_rate=annual_cash_rate,
            preannouncement_closes=tuple(
                float(value) for value in before_target["Close"].tail(20)
            ),
        ),
        None,
    )


def _catalog_port(path: Path | None) -> CatalogWindowPort:
    from aegis_data.catalog import catalog_data_port

    return catalog_data_port(path)


def _window_frames(
    port: CatalogWindowPort,
    instrument_ids: tuple[InstrumentId, ...],
    *,
    start: str,
    end: str,
) -> dict[InstrumentId, pd.DataFrame]:
    from aegis_data.catalog import CatalogWindowRequest

    return port.load_window(CatalogWindowRequest(instrument_ids, start, end, "1D")).ohlcv
