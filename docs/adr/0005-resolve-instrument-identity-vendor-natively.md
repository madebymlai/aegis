# Resolve instrument identity through vendor-native services, not a bespoke Security Master

Status: accepted (design; spike-validated against IB paper + Databento, 2026-06-19).
**Supersedes this ADR's earlier within-session draft** (a bespoke runtime "Security Master"
resolving an `InstrumentRef` to a venue-neutral `VenueContract`). Refines ADR-0002 and ADR-0003.

A live spike confirmed that the bespoke instrument-identity resolver we were about to build —
a Trader-side OpenFIGI client, a Bloomberg-exchange→MIC table, a `FuturesCalendar`, and a
runtime "Security Master" emitting a `VenueContract` — **reinvents services Aegis Trader already
depends on**. We do not build it.

The cross-context *identity* is unchanged: `InstrumentRef` (`ListedRef(figi)` |
`FuturesRef(root, dataset, roll_rule, adjustment)`) is still what the `DataContract` carries and
what Aegis RD **mints** at export. What changes is *resolution* at Trader:

1. **`ListedRef` → IB `InstrumentProvider`.** Hand the FIGI to Interactive Brokers:
   `IBContract(secType='STK', secIdType='FIGI', secId=figi, exchange='SMART')` with
   `convert_exchange_to_mic_venue=True`. IB returns the qualified listing, the MIC venue, the
   conId, currency, and tick. Spike: `BBG000B9XRY4 → AAPL.XNAS`, plus `SPY.ARCX`, `IBM.XNYS`,
   `AIGC.XLON`, `GBUS.XLON` — including the non-obvious `ARCA→ARCX`.
2. **`FuturesRef` → IBKR, via the `roll_rule`.** Live/paper resolution is **IBKR-only**:
   `Databento` and `yfinance` are *both research-only* substrates that define/validate the
   continuous series a futures strategy is backtested on (`FuturesRef.dataset` is a research tag,
   not in the live loop). At live, the `roll_rule` picks the front dated contract — from IB's chain
   expiries or a deterministic CME calendar — and Aegis Trader qualifies it at IB by its
   exchange-native Globex `localSymbol` (`6EU6`, `GCQ6`), on a delayed IBKR market-data
   subscription. **No IB `CONTFUT`** (historical-only at IB, and would substitute IB's roll for the
   research roll) and **no per-root map**. The `roll_rule` is the research↔live bridge: it must pick
   the same front contract on the research series and at IBKR. Spike: all 23 universe roots resolve
   at IB.
3. **The `InstrumentId ↔ InstrumentRef` inverse** (so the rebalancer reasons in continuous
   `InstrumentRef` space, per ADR-0003) is built from the provider's load results — we requested a
   known ref and record which `InstrumentId` came back.

## Considered options

- **Build the bespoke runtime Security Master + `VenueContract` + OpenFIGI client +
  Bloomberg→MIC table + `FuturesCalendar`** (the within-session draft of this ADR): rejected. The
  live spike showed IB's `InstrumentProvider` already resolves a FIGI to the correct listing and
  maps exchange→MIC, and IB qualifies a concrete dated future from vendor-supplied fields. Building
  our own duplicates a maintained vendor service and rots.
- **IB `CONTFUT` for futures continuity**: rejected. `CONTFUT` applies *IB's* roll, but
  research/backtest continuity is Aegis Data's Panama-adjusted chain; delegating the roll to IB
  would make live execution roll on a different rule than the strategy was validated on. IB
  `CONTFUT` symbology is also finicky per-root (spike: `GC:COMEX` resolved; `ZN`/`CL`/`6E` failed
  under guessed exchange codes, and one bad contract aborts the whole batch).

## Consequences

- **Bounded residuals, all vendor-owned.** (1) Equities: a small **MIC-override** set for IB
  exchange codes Nautilus does not map — spike: `IGLN → IGLN.LSEETF` needs `LSEETF→XLON` — via the
  provider's `symbol_to_mic_venue`. (2) Equities: **GBp/GBP** (pence) reconciliation for LSE
  instruments quoted in pence (spike: `GBUS` says `GBp`, IB reports `GBP`). (3) Futures: the **3
  COMEX metals** (`GC/SI/HG`) resolve on raw `COMEX` and need a one-line `COMEX→XCEC` override; the
  other 20 of 23 roots get a clean MIC venue automatically, and **FX resolves by `localSymbol`
  (`6EU6`)** so no `6E→EUR` symbol map is needed. All ride Nautilus's `VENUE_MEMBERS` — one line per
  *exchange*, zero per *instrument*.
- **Futures are provider-class-coupled by nature; equities are provider-agnostic.** Equities have a
  universal key (FIGI). Futures have none, so a `FuturesRef`'s continuity is bound to its `dataset`
  — but **live/paper is IBKR-only** (delayed market data + execution), so Databento/yfinance never
  enter the live loop. yfinance `=F` stitched front-months expose no dated contract and are
  **research-only, non-promotable**; any Globex-symbology dated-chain research source is swappable.
- **Backtest is unaffected.** It builds Nautilus instruments locally from definitions (resolution-
  via-IB is a live-boot concern). Definitions should increasingly come from Aegis Data's stored
  Databento definitions rather than hand-specified specs.
- **Retired (never built): the runtime Security Master and `VenueContract`. Deleted (existing):**
  the Trader `FigiInstrumentResolver`, its `_OpenFigiClient`, the `_bloomberg_exch_to_mic` table,
  and the `FuturesCalendar`/`FuturesContractResolver` aliases. `aegis-runtime` keeps only the
  `InstrumentRef` variant types.
- **RD's mint is unchanged** — `ticker → FIGI` via OpenFIGI at export, Nautilus-free. It is the
  only OpenFIGI use left, and a vendor lookup, not a hand-maintained map.
