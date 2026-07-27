#!/usr/bin/env python
"""PROTOTYPE - THROWAWAY. Does the AEB EUR line cost more to trade than the LSE USD line?

CONTEXT
-------
SDHY (IE00BCRY6003) and LQDH (IE00BCLWRB83) each list on BOTH London (LSEETF, USD) and
Amsterdam (AEB, EUR) under the SAME ISIN - same share class, different trading currency.
Trading the AEB line would avoid the USD margin debit (5.13%/yr) and the per-rebalance FX
conversion the book currently pays.

That saving is only real if the AEB line is not materially less liquid. A wider spread paid
on every rebalance can easily exceed a financing saving. THIS IS THE TEST.

MEASURES (all from IBKR historical bars - no live subscription needed)
  1. TRADES   -> average daily volume and traded value: is anyone there?
  2. BID_ASK  -> average quoted spread in basis points: what does crossing cost?

The decision rule stated BEFORE looking: the AEB line is preferable only if its spread is
within a few bp of London's. The financing saving is ~5.13%/yr on the USD debit, but it is
earned continuously while the spread is paid per trade, so the comparison must be made
against the sleeve's actual turnover, not in the abstract. This probe supplies the spread
number; it does not by itself decide the swap.

    AEGIS_IBKR_GATEWAY_PORT=4002 python _prototyping/at1_access/liquidity.py
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

from ibapi.client import EClient  # type: ignore[import-not-found]
from ibapi.contract import Contract  # type: ignore[import-not-found]
from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]

# (label, symbol, exchange, currency) - the two venues of each identical share class.
VENUES = [
    ("SDHY London", "SDHY", "LSEETF", "USD"),
    ("SDHY Amsterdam", "SDHY", "AEB", "EUR"),
    ("LQDH London", "LQDH", "LSEETF", "USD"),
    ("LQDH Amsterdam", "LQDH", "AEB", "EUR"),
    ("XAT1 SIX", "XAT1", "EBS", "EUR"),
]
DURATION = "3 M"

PORT = int(os.environ.get("AEGIS_IBKR_GATEWAY_PORT", "4002"))
HOST = os.environ.get("AEGIS_IBKR_GATEWAY_HOST", "127.0.0.1")
CLIENT_ID = int(os.environ.get("AEGIS_IBKR_CLIENT_ID", "78"))


class Probe(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.bars: dict[int, list] = defaultdict(list)
        self.done: set[int] = set()
        self.errors: dict[int, list[str]] = defaultdict(list)

    def nextValidId(self, orderId: int) -> None:  # noqa: N803
        self.ready.set()

    def error(self, reqId, *args):  # noqa: N803
        msg = " ".join(str(a) for a in args)
        if reqId is not None and reqId >= 0:
            self.errors[reqId].append(msg)
            self.done.add(reqId)

    def historicalData(self, reqId: int, bar) -> None:  # noqa: N803
        self.bars[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:  # noqa: N803
        self.done.add(reqId)


def _contract(symbol: str, exchange: str, currency: str) -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = exchange
    c.currency = currency
    return c


def main() -> None:
    app = Probe()
    app.connect(HOST, PORT, clientId=CLIENT_ID)
    threading.Thread(target=app.run, daemon=True).start()
    if not app.ready.wait(15):
        print(f"FAILED to connect at {HOST}:{PORT}")
        return
    print(f"connected {HOST}:{PORT}  duration={DURATION}\n")

    ids: dict[int, tuple[str, str]] = {}
    rid = 300
    for label, sym, exch, ccy in VENUES:
        for what in ("TRADES", "BID_ASK"):
            ids[rid] = (label, what)
            app.reqHistoricalData(
                rid, _contract(sym, exch, ccy), "", DURATION, "1 day", what, 1, 1, False, []
            )
            rid += 1
            time.sleep(2.2)  # IBKR paces historical requests hard

    deadline = time.time() + 90
    while time.time() < deadline and not set(ids) <= app.done:
        time.sleep(0.5)

    trades: dict[str, tuple] = {}
    spreads: dict[str, float] = {}
    for r, (label, what) in ids.items():
        bars = app.bars.get(r, [])
        if not bars:
            err = "; ".join(app.errors.get(r, []))[:70] or "no data"
            print(f"  {label:<18} {what:<8} NO DATA  {err}")
            continue
        if what == "TRADES":
            vols = [b.volume for b in bars if b.volume and b.volume > 0]
            closes = [b.close for b in bars if b.close]
            if vols and closes:
                avg_v = sum(vols) / len(vols)
                px = sum(closes) / len(closes)
                trades[label] = (avg_v, px, avg_v * px, len(bars), len(vols))
        else:
            # BID_ASK bars: open=avg bid, close=avg ask (IBKR convention), high/low = extremes
            rel = [
                (b.close - b.open) / ((b.close + b.open) / 2.0)
                for b in bars
                if b.open and b.close and b.close > b.open
            ]
            if rel:
                rel.sort()
                spreads[label] = 1e4 * rel[len(rel) // 2]  # median, bp

    print(f"\n  {'VENUE':<18} {'AVG DAILY VOL':>14} {'PX':>9} {'DAILY VALUE':>14} {'SPREAD bp':>11}")
    print("  " + "-" * 70)
    for label, *_ in [(v[0],) for v in VENUES]:
        t = trades.get(label)
        s = spreads.get(label)
        vol = f"{t[0]:>14,.0f}" if t else f"{'-':>14}"
        px = f"{t[1]:>9,.2f}" if t else f"{'-':>9}"
        val = f"{t[2]:>14,.0f}" if t else f"{'-':>14}"
        sp = f"{s:>11.1f}" if s is not None else f"{'-':>11}"
        print(f"  {label:<18} {vol} {px} {val} {sp}")
        if t:
            print(f"  {'':<18}   ({t[4]}/{t[3]} bars had nonzero volume)")

    print("\n  NOTE: daily value is in the venue's own currency (USD for London, EUR for")
    print("        Amsterdam/SIX) - roughly comparable at ~1.08 EURUSD, not exactly.")
    print("        Spread is the median of (avg_ask - avg_bid)/mid from daily BID_AASK bars,")
    print("        which understates the spread an actual marketable order crosses.")
    app.disconnect()


if __name__ == "__main__":
    main()
