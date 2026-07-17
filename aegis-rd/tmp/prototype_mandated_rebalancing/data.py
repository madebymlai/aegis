"""PROTOTYPE (throwaway) — data loading for the mandated-rebalancing prototype.

Separate from the engine on purpose: the engine sees plain return arrays only.

Sources, in order of preference:
  * IBKR (repository standard for futures) — CONTFUT daily closes for ES / ZN /
    TN via the gateway on 127.0.0.1:4002, plus QSPX / MTN when discoverable.
    Currently gated on the historical-data farm accepting requests.
  * Yahoo chart API fallback — continuous front-month ES=F / ZN=F / TN=F
    (unadjusted splices: ~4 roll joints/yr add small non-tradeable jumps),
    ^GSPC / ^TNX / ^IRX for the pre-2000 proxy extension and cross-checks.

Cache: CSV files under data_cache/ next to this file. PROTOTYPE — wipe freely.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent / "data_cache"

YAHOO_SYMBOLS = {
    "es": "ES=F",  # E-mini S&P 500, continuous front month
    "zn": "ZN=F",  # 10-year T-note (conventional), continuous front month
    "tn": "TN=F",  # Ultra 10-year, continuous front month (MTN exposure proxy)
    "spx": "^GSPC",
    "tnx": "^TNX",  # 10y yield
    "irx": "^IRX",  # 13-week T-bill discount rate
}

IBKR_CONTRACTS = {
    "es": ("ES", "CME"),
    "zn": ("ZN", "CBOT"),
    "tn": ("TN", "CBOT"),
    "qspx": ("QSPX", "CME"),  # spot-quoted S&P 500, $1 x index, launched 2025
    "mtn": ("MTN", "CBOT"),  # Micro Ultra 10y, $10k face, listed since 2024-08
}

# Pre-2000 stock proxy: index price return + (dividend yield - T-bill)/252.
PROXY_DIVIDEND_YIELD = 0.015  # documented constant for 1997-2000, not fitted
PROXY_BOND_DURATION = 6.5  # ~ZN CTD modified duration, documented constant

PAPER_START = "1997-09-10"
PAPER_END = "2023-03-17"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _yahoo_fetch(symbol: str) -> pd.Series:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.request.quote(symbol)
        + "?interval=1d&period1=0&period2=9999999999"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    result = payload["chart"]["result"][0]
    stamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    index = pd.to_datetime(stamps, unit="s", utc=True).tz_convert("America/New_York")
    series = pd.Series(closes, index=index.normalize().tz_localize(None), dtype=float)
    series = series.dropna()
    return series[~series.index.duplicated(keep="last")].sort_index()


def fetch_yahoo(refresh: bool = False) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    (CACHE_DIR / "README.txt").write_text(
        "PROTOTYPE data cache - wipe me freely; refetch with:\n"
        "uv run python tmp/prototype_mandated_rebalancing/data.py fetch\n"
    )
    for key, symbol in YAHOO_SYMBOLS.items():
        path = CACHE_DIR / f"yahoo_{key}.csv"
        if path.exists() and not refresh:
            continue
        series = _yahoo_fetch(symbol)
        series.rename("close").rename_axis("date").to_csv(path)
        print(f"fetched {symbol}: {len(series)} rows {series.index[0].date()}"
              f" .. {series.index[-1].date()}")


def fetch_ibkr(host: str = "127.0.0.1", port: int = 4002) -> dict[str, str]:
    """Attempt CONTFUT daily history via the gateway; returns per-key status."""
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.wrapper import EWrapper

    class App(EWrapper, EClient):
        def __init__(self) -> None:
            EClient.__init__(self, self)
            self.bars: dict[int, list[tuple[str, float]]] = defaultdict(list)
            self.done: set[int] = set()
            self.errors: dict[int, list[str]] = defaultdict(list)
            self.ready = threading.Event()

        def nextValidId(self, orderId):  # noqa: N802
            self.ready.set()

        def historicalData(self, reqId, bar):  # noqa: N802
            self.bars[reqId].append((bar.date, float(bar.close)))

        def historicalDataEnd(self, reqId, start, end):  # noqa: N802
            self.done.add(reqId)

        def error(self, reqId, *args):
            message = " ".join(str(a) for a in args)
            if reqId is not None and reqId >= 0:
                self.errors[reqId].append(message)
                if any(code in message for code in ("162", "200", "354", "10167")):
                    self.done.add(reqId)

    app = App()
    app.connect(host, port, clientId=219)
    threading.Thread(target=app.run, daemon=True).start()
    if not app.ready.wait(timeout=15):
        app.disconnect()
        return {key: "gateway unreachable" for key in IBKR_CONTRACTS}

    CACHE_DIR.mkdir(exist_ok=True)
    status: dict[str, str] = {}
    request_id = 0
    for key, (symbol, exchange) in IBKR_CONTRACTS.items():
        request_id += 1
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "CONTFUT"
        contract.exchange = exchange
        contract.currency = "USD"
        app.reqHistoricalData(
            reqId=request_id,
            contract=contract,
            endDateTime="",
            durationStr="30 Y",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=0,
            formatDate=1,
            keepUpToDate=False,
            chartOptions=[],
        )
        deadline = time.time() + 180
        while time.time() < deadline and request_id not in app.done:
            time.sleep(0.1)
        bars = app.bars.get(request_id, [])
        if bars:
            index = pd.to_datetime([b[0] for b in bars], format="%Y%m%d")
            series = pd.Series([b[1] for b in bars], index=index, name="close")
            series = series[~series.index.duplicated(keep="last")].sort_index()
            series.rename_axis("date").to_csv(CACHE_DIR / f"ibkr_{key}.csv")
            status[key] = (
                f"ok {len(series)} rows {series.index[0].date()}"
                f" .. {series.index[-1].date()}"
            )
        else:
            status[key] = "; ".join(app.errors.get(request_id, ["no data"]))[:120]
        time.sleep(2)
    app.disconnect()
    return status


# ---------------------------------------------------------------------------
# Loading + series assembly
# ---------------------------------------------------------------------------


def _load_source(key: str, source: str) -> pd.Series | None:
    path = CACHE_DIR / f"{source}_{key}.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path, parse_dates=["date"], index_col="date")
    series = frame["close"].dropna()
    series.attrs["source"] = source
    return series


def _load(key: str) -> pd.Series | None:
    """Longest history wins: IBKR CONTFUT only reaches back ~2-4 years, so the
    reproduction windows come from Yahoo; the IBKR copy stays as a cross-check."""
    candidates = [s for s in (_load_source(key, "ibkr"), _load_source(key, "yahoo"))
                  if s is not None]
    if not candidates:
        return None
    return max(candidates, key=len)


def _yield_fraction(series: pd.Series) -> pd.Series:
    # ^TNX/^IRX are quoted either as percent or 10x percent depending on era.
    scaled = series / 10.0 if series.median() > 20 else series
    return scaled / 100.0


class DataUnavailable(RuntimeError):
    pass


def load_market_inputs() -> dict[str, pd.Series | None]:
    keys = ("es", "zn", "tn", "spx", "tnx", "irx", "qspx", "mtn")
    series = {key: _load(key) for key in keys}
    if series["es"] is None or series["zn"] is None:
        raise DataUnavailable(
            "no cached ES/ZN series; run: uv run python "
            "tmp/prototype_mandated_rebalancing/data.py fetch"
        )
    return series


def futures_returns(close: pd.Series) -> pd.Series:
    return close.pct_change().dropna()


def proxy_extension(
    spx: pd.Series, tnx: pd.Series, irx: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """Pre-futures 1997..2000 proxies: labeled approximations, not futures data."""
    rf_daily = _yield_fraction(irx) / 252.0
    stock = (
        spx.pct_change() + (PROXY_DIVIDEND_YIELD / 252.0) - rf_daily.reindex(spx.index)
    ).dropna()
    yield_series = _yield_fraction(tnx)
    delta_yield = yield_series.diff()
    carry = yield_series.shift(1) / 252.0
    bond = (
        -PROXY_BOND_DURATION * delta_yield
        + carry
        - rf_daily.reindex(yield_series.index)
    ).dropna()
    return stock, bond


def spread_inputs(
    series: dict[str, pd.Series | None], extend_proxy: bool
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, list[str]]:
    """Aligned daily stock/bond futures return arrays plus caveat notes."""
    notes: list[str] = []
    stock = futures_returns(series["es"])
    bond = futures_returns(series["zn"])
    notes.append(f"ES source: {series['es'].attrs.get('source')}"
                 f" ({series['es'].index[0].date()}..)")
    notes.append(f"ZN source: {series['zn'].attrs.get('source')}"
                 f" ({series['zn'].index[0].date()}..)")
    if series["es"].attrs.get("source") == "yahoo":
        notes.append("continuous splice unadjusted: ~4 roll joints/yr per leg")
    if extend_proxy:
        if series["spx"] is None or series["tnx"] is None or series["irx"] is None:
            notes.append("proxy extension requested but index/yield series missing")
        else:
            proxy_stock, proxy_bond = proxy_extension(
                series["spx"], series["tnx"], series["irx"]
            )
            start = pd.Timestamp(PAPER_START)
            proxy_stock = proxy_stock[
                (proxy_stock.index >= start) & (proxy_stock.index < stock.index[0])
            ]
            proxy_bond = proxy_bond[
                (proxy_bond.index >= start) & (proxy_bond.index < bond.index[0])
            ]
            stock = pd.concat([proxy_stock, stock])
            bond = pd.concat([proxy_bond, bond])
            notes.append(
                f"{PAPER_START}..{proxy_stock.index[-1].date() if len(proxy_stock) else '-'}"
                " is an INDEX/YIELD PROXY (SPX price + div - rf; -6.5*dYield + carry),"
                " not futures data"
            )
    aligned = pd.concat(
        [stock.rename("stock"), bond.rename("bond")], axis=1, join="inner"
    ).dropna()
    return (
        pd.DatetimeIndex(aligned.index),
        aligned["stock"].to_numpy(),
        aligned["bond"].to_numpy(),
        notes,
    )


def contract_notionals(
    series: dict[str, pd.Series | None], dates: pd.DatetimeIndex
) -> tuple[pd.Series, pd.Series, list[str]]:
    """Per-date USD notionals: QSPX ($1 x SPX) and MTN ($10k face Ultra-10y)."""
    notes = []
    if series["spx"] is not None:
        qspx = series["spx"].reindex(dates).ffill()
    else:
        qspx = pd.Series(5000.0, index=dates)
        notes.append("SPX level missing; QSPX notional pinned to $5000")
    if series["tn"] is not None:
        mtn = series["tn"].reindex(dates).ffill() * 100.0
        notes.append(
            f"MTN notional/returns proxied by TN (Ultra 10y, source "
            f"{series['tn'].attrs.get('source')}); actual MTN history starts 2025 "
            "and is not in cache - SYNTHETIC pre-launch, cannot establish live "
            "liquidity or tracking"
        )
    else:
        mtn = pd.Series(11_000.0, index=dates)
        notes.append("TN series missing; MTN notional pinned to $11000")
    return qspx, mtn, notes


def cross_checks(series: dict[str, pd.Series | None]) -> list[str]:
    """Data-quality gates: continuous futures vs index/yield sanity."""
    notes = []
    for key in ("es", "zn"):
        ibkr = _load_source(key, "ibkr")
        yahoo = _load_source(key, "yahoo")
        if ibkr is None or yahoo is None:
            continue
        joined = pd.concat(
            [futures_returns(ibkr).rename("ibkr"),
             futures_returns(yahoo).rename("yahoo")],
            axis=1, join="inner",
        ).dropna()
        if len(joined) > 100:
            correlation = joined.corr().iloc[0, 1]
            notes.append(
                f"{key.upper()} IBKR vs Yahoo overlap ({joined.index[0].date()}.., "
                f"n={len(joined)}): corr {correlation:.3f} "
                f"({'OK' if correlation > 0.97 else 'SUSPECT'})"
            )
    if series["es"] is not None and series["spx"] is not None:
        es_returns = futures_returns(series["es"])
        spx_returns = series["spx"].pct_change().dropna()
        joined = pd.concat([es_returns, spx_returns], axis=1, join="inner").dropna()
        if len(joined) > 100:
            correlation = joined.corr().iloc[0, 1]
            notes.append(f"ES vs SPX daily return corr {correlation:.3f} "
                         f"({'OK' if correlation > 0.95 else 'SUSPECT'})")
    if series["zn"] is not None and series["tnx"] is not None:
        zn_returns = futures_returns(series["zn"])
        implied = -PROXY_BOND_DURATION * _yield_fraction(series["tnx"]).diff()
        joined = pd.concat([zn_returns, implied], axis=1, join="inner").dropna()
        if len(joined) > 100:
            correlation = joined.corr().iloc[0, 1]
            notes.append(f"ZN vs -6.5*dYield daily corr {correlation:.3f} "
                         f"({'OK' if correlation > 0.85 else 'SUSPECT'})")
    if series["tn"] is not None and series["zn"] is not None:
        tn_returns = futures_returns(series["tn"])
        zn_returns = futures_returns(series["zn"])
        joined = pd.concat(
            [tn_returns.rename("tn"), zn_returns.rename("zn")], axis=1, join="inner"
        ).dropna()
        if len(joined) > 100:
            ratio = joined["tn"].std() / joined["zn"].std()
            correlation = joined.corr().iloc[0, 1]
            notes.append(
                f"Ultra-10y (TN) vs conventional (ZN): corr {correlation:.3f}, "
                f"vol ratio {ratio:.2f} (the MTN exposure mismatch)"
            )
    return notes


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if command == "fetch":
        fetch_yahoo(refresh="--refresh" in sys.argv)
        print("attempting IBKR CONTFUT (repository-standard source)...")
        try:
            for key, state in fetch_ibkr().items():
                print(f"  ibkr {key}: {state}")
        except Exception as error:  # noqa: BLE001 - prototype: report and continue
            print(f"  ibkr unavailable: {error}")
        for note in cross_checks(load_market_inputs()):
            print("check:", note)
    else:
        print(f"unknown command {command!r}; use: fetch [--refresh]")
