#!/usr/bin/env python
"""PROTOTYPE - THROWAWAY. Audits an unverified claim; verdict folds into the Demeter notes.

QUESTION
--------
An agent search claimed three natively-EUR credit ETFs "were verified to exist" and that
claim was passed into `the-premium-is-rent-on-a-balance-sheet.md` (the "remove the currency
and financing tax" recommendation) WITHOUT a broker check:

  - ATEA       - AT1 contingent-convertible bank capital, 0.39% TER
  - PCL0/EUCL  - EUR CLO senior, 0.25% TER
  - IMBE       - EUR-hedged agency MBS, 0.30% TER

Does IBKR actually list them, and on what venue/currency?

METHOD - two passes, both READ-ONLY (no orders, not even whatIf):
  1. reqMatchingSymbols on free-text patterns. This is IBKR's OWN search, so it does not
     depend on guessing tickers correctly - the failure mode that cost the cross-market VRP
     probe 26 dead guesses.
  2. reqContractDetails per candidate ticker with exchange="" (all listings) so IBKR returns
     every venue/currency pair it knows for that symbol.

LIMITATION, STATED UP FRONT: contract details prove the instrument is LISTED. They do not
prove this account may trade it. Trading permissions, market-data entitlement and the PRIIPs
KID availability for an EU retail account are all separate gates. A green result here is
necessary, not sufficient.

HOW TO RUN (operator only - needs the data line free; single session per login)
    AEGIS_IBKR_GATEWAY_PORT=4002 uv run --with ibapi python _prototyping/at1_access/probe.py

No persistence, no tests, no abstractions. Prints a matrix and exits.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import defaultdict

from ibapi.client import EClient  # type: ignore[import-not-found]
from ibapi.contract import Contract  # type: ignore[import-not-found]
from ibapi.wrapper import EWrapper  # type: ignore[import-not-found]

# Pass 1: IBKR's own search. Patterns, not guesses.
SEARCH_PATTERNS = ["AT1", "ATEA", "CoCo", "COCB", "EUCL", "IMBE", "PCL0"]

# Pass 2: candidate tickers. The three claimed names, plus the sibling share classes and
# competitor products that would be the fallback if the claimed ticker is wrong.
CANDIDATES = [
    # --- claimed in the note ---
    "ATEA",   # AT1 CoCo, EUR hedged acc (claimed)
    "EUCL",   # EUR CLO senior (claimed)
    "PCL0",   # EUR CLO senior, alt listing (claimed)
    "IMBE",   # EUR-hedged agency MBS (claimed)
    # --- AT1 CoCo siblings / competitors ---
    "AT1",    # Invesco AT1 Capital Bond UCITS ETF, LSE USD
    "AT1D",
    "AT1E",
    "CCBO",   # WisdomTree AT1 CoCo Bond UCITS ETF
    "COCB",
    "COCO",
    # --- CLO / MBS competitors ---
    "CLOA",   # Fair Oaks / Janus Henderson AAA CLO
    "JAAA",   # Janus Henderson AAA CLO (US, control - should exist)
    "MBSE",
]

# argv overrides the lists above:  probe.py [--search p1,p2] [--tickers t1,t2]
def _argv_override() -> None:
    global SEARCH_PATTERNS, CANDIDATES
    argv = sys.argv[1:]
    for flag, target in (("--search", "SEARCH_PATTERNS"), ("--tickers", "CANDIDATES")):
        if flag in argv:
            vals = [v.strip() for v in argv[argv.index(flag) + 1].split(",") if v.strip()]
            globals()[target] = vals


PORT = int(os.environ.get("AEGIS_IBKR_GATEWAY_PORT", "4002"))
HOST = os.environ.get("AEGIS_IBKR_GATEWAY_HOST", "127.0.0.1")
CLIENT_ID = int(os.environ.get("AEGIS_IBKR_CLIENT_ID", "77"))


class Probe(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.matches: dict[int, list[tuple]] = defaultdict(list)
        self.details: dict[int, list[tuple]] = defaultdict(list)
        self.done: set[int] = set()
        self.errors: dict[int, list[str]] = defaultdict(list)

    def nextValidId(self, orderId: int) -> None:  # noqa: N803
        self.ready.set()

    def error(self, reqId, *args):  # noqa: N803  # version-tolerant (ibapi 9.x/10.x)
        msg = " ".join(str(a) for a in args)
        if reqId is not None and reqId >= 0:
            self.errors[reqId].append(msg)
            # 200 = no security definition found; terminal for that request
            if "200" in msg:
                self.done.add(reqId)

    def symbolSamples(self, reqId: int, contractDescriptions) -> None:  # noqa: N803
        for cd in contractDescriptions:
            c = cd.contract
            self.matches[reqId].append(
                (c.symbol, c.secType, c.primaryExchange, c.currency, getattr(cd, "derivativeSecTypes", ""))
            )
        self.done.add(reqId)

    def contractDetails(self, reqId: int, contractDetails) -> None:  # noqa: N803
        c = contractDetails.contract
        self.details[reqId].append(
            (
                c.symbol,
                c.secType,
                c.exchange,
                c.primaryExchange,
                c.currency,
                contractDetails.longName,
                next((x.value for x in (contractDetails.secIdList or []) if x.tag == "ISIN"), "?"),
            )
        )

    def contractDetailsEnd(self, reqId: int) -> None:  # noqa: N803
        self.done.add(reqId)


def _wait(app: Probe, req_ids: list[int], timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not set(req_ids) <= app.done:
        time.sleep(0.2)


def main() -> None:
    _argv_override()
    app = Probe()
    app.connect(HOST, PORT, clientId=CLIENT_ID)
    threading.Thread(target=app.run, daemon=True).start()
    if not app.ready.wait(15):
        print(f"FAILED to connect to gateway at {HOST}:{PORT} (client {CLIENT_ID})")
        return
    print(f"connected {HOST}:{PORT} client={CLIENT_ID}\n")

    # ---- Pass 1: IBKR's own symbol search --------------------------------
    print("=" * 78)
    print("PASS 1  reqMatchingSymbols - IBKR's own search (no ticker guessing)")
    print("=" * 78)
    ids = []
    for i, pat in enumerate(SEARCH_PATTERNS):
        rid = 1000 + i
        ids.append(rid)
        app.reqMatchingSymbols(rid, pat)
        time.sleep(1.1)  # IBKR rate-limits symbol search to ~1/sec
    _wait(app, ids)
    for i, pat in enumerate(SEARCH_PATTERNS):
        rid = 1000 + i
        hits = app.matches.get(rid, [])
        print(f"\n  pattern {pat!r}: {len(hits)} hit(s)")
        for sym, sec, prim, ccy, deriv in hits[:12]:
            print(f"      {sym:<10} {sec:<6} {prim or '-':<12} {ccy:<5} {deriv}")
        for e in app.errors.get(rid, []):
            print(f"      ERR {e}")

    # ---- Pass 2: per-ticker contract details -----------------------------
    print("\n" + "=" * 78)
    print("PASS 2  reqContractDetails - all listings per candidate (exchange='')")
    print("=" * 78)
    ids = []
    for i, sym in enumerate(CANDIDATES):
        rid = 2000 + i
        ids.append(rid)
        c = Contract()
        c.symbol = sym
        c.secType = "STK"
        c.exchange = ""  # all venues IBKR knows
        app.reqContractDetails(rid, c)
        time.sleep(0.4)
    _wait(app, ids, timeout=40.0)

    print(f"\n  {'TICKER':<8} {'STATUS':<10} LISTINGS")
    print("  " + "-" * 74)
    for i, sym in enumerate(CANDIDATES):
        rid = 2000 + i
        rows = app.details.get(rid, [])
        if not rows:
            why = "; ".join(app.errors.get(rid, [])) or "no response"
            print(f"  {sym:<8} {'ABSENT':<10} {why[:60]}")
            continue
        venues = sorted({(r[3] or r[2], r[4], r[6]) for r in rows})
        name = rows[0][5]
        print(f"  {sym:<8} {'LISTED':<10} {name[:52]}")
        for prim, ccy, isin in venues:
            print(f"  {'':<8} {'':<10}   -> {prim:<14} {ccy:<5} {isin}")

    app.disconnect()
    print("\nNOTE: LISTED proves the contract exists, NOT that this account may trade it.")
    print("      Permissions, market data and PRIIPs KID are separate gates.")


if __name__ == "__main__":
    main()
