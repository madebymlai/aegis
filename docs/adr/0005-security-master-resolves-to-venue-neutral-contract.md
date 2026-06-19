# The Security Master resolves to a venue-neutral `VenueContract`; the Nautilus binding is a Trader adapter

Status: accepted (design; implementation pending). Refines ADR-0002 (Security Master placement
rationale) and ADR-0003 (`resolve(ref, as_of)` resolution target). Depends on the `aegis-runtime`
carve-out.

ADR-0002/0003 placed the **Security Master** in `aegis-runtime` *and* had it resolve an
`InstrumentRef` to a Nautilus `InstrumentId`. Those two cannot both hold. `aegis-runtime` is the
lean shared kernel (numpy/pandas only) that **Aegis RD depends on**, and RD is deliberately
**Nautilus-free** (NautilusTrader's Rust runtime forces the process multi-threaded on import). A
resolver that imports `nautilus_trader` cannot live in `aegis-runtime` without transitively pulling
Nautilus into RD — destroying the boundary RD exists to protect. Today the resolver
(`FigiInstrumentResolver`) lives in `aegis-trader/aegis_trader/execution/figi_resolver.py`, not in
runtime, contradicting the glossary and ADR-0002.

We resolve it by **splitting**, not moving:

1. **The Security Master resolves `InstrumentRef → VenueContract`.** `VenueContract` is a new
   runtime-owned value type: a venue-addressing, broker-neutral `{symbol, venue}` pair
   (`AAPL`/`XNAS`, `ESM5`/`XCME`). It names a tradable contract in venue symbology but carries no
   broker binding. One `VenueContract` serves **both** variants — a `ListedRef` resolves to a
   date-invariant one, a `FuturesRef` to the live dated contract as-of a date.
2. **A Trader-side adapter binds `VenueContract → InstrumentId / conId`.** A Nautilus `InstrumentId`
   is literally `f"{symbol}.{venue}"`, so the binding collapses to a string format; the IBKR `conId`
   stays the isolated broker seam (ADR-0003). This deletes the injected
   `FuturesContractResolver` alias (which referenced Nautilus `InstrumentId`).
3. **Mint ≠ resolve.** RD's `ticker→FIGI` step (`market_data/figi.py`) **mints** the `InstrumentRef`
   at export and stays RD-owned — it speaks RD-config vocabulary (`SymbolSpec`, `mic`, `isin`). It is
   *not* the Security Master. Only the genuinely-duplicated **OpenFIGI client + `FigiResolutionError`**
   consolidate into runtime (`aegis_runtime/openfigi.py`); RD's mint and the Security Master both call
   it. The resolution *rules* (`TICKER`/`ISIN` jobs vs `FIGI`-to-exchange-metadata) are different and
   are **not** merged.
4. **The inverse splits two-hop.** The Security Master owns the stateful `VenueContract ↔ InstrumentRef`
   bijection (including which dated contract a `FuturesRef` resolved to); the Trader adapter owns the
   pure `InstrumentId ↔ VenueContract` string mapping. The domain rebalancer keeps seeing only
   `InstrumentRef`.
5. **Rename.** `FigiInstrumentResolver → SecurityMaster` in `aegis_runtime/security_master.py`. The
   class is asset-agnostic; "Figi" is the equity-shaped framing ADR-0003 set out to kill (FIGI is only
   the `ListedRef` variant's identity).

## Considered options

- **`aegis-runtime` takes a `nautilus_trader` dependency** (move the resolver as-is): rejected. RD
  depends on `aegis-runtime`, so it inherits Nautilus transitively — the exact coupling RD is built
  to avoid.
- **Keep resolve-out in Aegis Trader** (its only production consumer) and hoist only the OpenFIGI
  client + `VenueContract` type: rejected. `InstrumentRef` is a sealed variant type *defined in
  runtime*; resolution switches on the variant. Splitting per-variant resolution from the variant
  definitions means every new asset class (e.g. crypto, ADR-0003's Forward-First case) touches **two
  packages across a context seam** — an Information-Hiding / OCP-locality violation. Co-locating the
  sealed resolution with the variants is why runtime is the right home — **not** ADR-0002's stated
  reason that "export must resolve ticker→FIGI as well." Export *mints*; it does not *resolve*. The
  resolve-out machinery is not shared with export.

## Consequences

- **`aegis-runtime` stays Nautilus-free and market-data-free.** It grows the OpenFIGI client (with a
  lazily-imported `requests` transport, test-injectable), the Bloomberg-exchange→MIC table, and the
  `SecurityMaster` + `VenueContract`. These are identity vocabulary — on-charter for the kernel.
- **ADR-0002's runtime-placement rationale is corrected here.** The decision (runtime) stands; the
  *reason* (shared with export) was a conflation of mint and resolve.
- **The futures roll calendar stays injected.** Picking the live dated contract as-of a date needs
  futures expiry data (Aegis Data), which must not enter the kernel. Runtime owns the resolution
  *logic*; the dated-contract calendar is supplied from outside. The futures path is an unwired,
  test-only mechanism today (no production `FuturesCalendar` exists), so the first concrete calendar
  is written *after* this move, against the runtime home, emitting `VenueContract`. Whether `RollRule`
  becomes an internal seam is still deferred to ADR-0003's "second roll rule" trigger.
