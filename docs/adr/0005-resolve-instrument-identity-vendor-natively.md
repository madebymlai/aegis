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
2. **`FuturesRef` → Databento definition + IB qualify.** Aegis Data already owns the contract
   chain and the roll (Panama back-adjustment, `aegis-data/aegis_data/continuous.py`) and loads
   Databento instrument **definitions** (`databento_port.get_range_instruments`). Given
   `FuturesRef + as_of` it yields the front dated contract's definition (symbol, month, venue);
   Aegis Trader qualifies *that concrete dated contract* at IB. **No IB `CONTFUT`** (that would
   substitute IB's roll for Aegis Data's), and **no per-root map** — the identity is read from the
   vendor definition, not hand-maintained.
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

- **Two bounded residuals, both vendor-owned.** (1) A small **MIC-override** set for IB exchange
  codes Nautilus does not map — spike: `IGLN → IGLN.LSEETF` needs `LSEETF→XLON` — via the
  provider's per-symbol override. (2) **GBp/GBP** (pence) reconciliation for LSE instruments quoted
  in pence (spike: `GBUS` config says `GBp`, IB reports `GBP`). These are ADR-0002's "one bounded
  table" residual, now layered on Nautilus's maintained exchange→MIC map: one line per *exchange*,
  zero per *instrument*.
- **Backtest is unaffected.** It builds Nautilus instruments locally from definitions (resolution-
  via-IB is a live-boot concern). Definitions should increasingly come from Aegis Data's stored
  Databento definitions rather than hand-specified specs.
- **Retired (never built): the runtime Security Master and `VenueContract`. Deleted (existing):**
  the Trader `FigiInstrumentResolver`, its `_OpenFigiClient`, the `_bloomberg_exch_to_mic` table,
  and the `FuturesCalendar`/`FuturesContractResolver` aliases. `aegis-runtime` keeps only the
  `InstrumentRef` variant types.
- **RD's mint is unchanged** — `ticker → FIGI` via OpenFIGI at export, Nautilus-free. It is the
  only OpenFIGI use left, and a vendor lookup, not a hand-maintained map.
