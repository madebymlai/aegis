# Identify cross-boundary instruments by FIGI, resolved through a shared Security Master

Status: accepted (implementation pending; depends on the `aegis-runtime` carve-out
and the `DataContract` from issue #40 / `aegis-rd-qcj`). **Refined by ADR-0003**: the
canonical cross-boundary identity is generalised from a bare FIGI to an asset-agnostic
`InstrumentRef` (FIGI becomes the `ListedRef` variant), and the Security Master resolves
*as-of* a date. The FIGI/`ListedRef` path below is unchanged; futures use `FuturesRef`.
**Superseded in part by ADR-0005** (spike-validated against IB paper, 2026-06-19): there is **no
bespoke Security Master**. Aegis Trader resolves a `ListedRef` by handing its FIGI to the IB
`InstrumentProvider` (`secIdType='FIGI'` + `convert_exchange_to_mic_venue`), which returns the
qualified listing and the MIC venue directly. The "Security Master is a deep module in
`aegis-runtime`" consequence below is **withdrawn** — equity identity resolves IB-native, RD's
`ticker→FIGI` mint stays, and the bounded residual is Nautilus's maintained exchange→MIC map plus a
tiny override set (one line per exchange, zero per instrument).

An **Execution Bundle**, **Aegis Trader**, and the live venue (Interactive Brokers via
**NautilusTrader**) must agree on *which instrument* a signed target weight refers to.
We make the canonical cross-boundary instrument identity the **FIGI** (OpenFIGI), not
the data-provider ticker. `aerd export` resolves each instrument's provider ticker to
its FIGI once, at export, and bakes it into the bundle's `DataContract`; the bundle's
signed target-weight frame is keyed by FIGI. A shared **Security Master** in
`aegis-runtime` resolves `FIGI → venue contract` (Nautilus `InstrumentId` / IBKR
`IBContract`) at startup, **fail-closed on ambiguity**. The commingling overlay nets in
canonical FIGI space and resolves to a Nautilus `InstrumentId` only at the execution
edge. OpenFIGI (Bloomberg, free, authoritative) is the mapping authority, so no
per-instrument symbol map is hand-maintained.

This follows the security-master pattern used by production trading systems: a single
security maps to many symbologies, so a durable canonical identifier is the hub and
ticker/CUSIP/ISIN/FIGI/venue-contract are spokes mapped to it. Research/analysis keys on
the durable id; execution uses venue-specific symbology — which is exactly Nautilus's
`InstrumentId = {symbol}.{venue}` model.

## Considered options

- **Provider ticker as the cross-boundary key** (`{ticker, ccy}`, the status quo in
  `carry.yaml`): rejected. The ticker is *provider-formatted* (yfinance `IHYU.L`,
  Bloomberg `IHYU LN`, …); resolving it requires knowing the format, which couples Trader
  to RD's choice of `data.source`. A ticker is not a primary key — one security maps to
  many symbologies across systems and changes under corporate actions.
- **ISIN (+ currency + MIC)**: rejected. Securities-only. Native crypto has no ISIN (it
  uses DTI / venue pair symbols) and MIC does not apply to crypto venues, so an ISIN key
  breaks the moment the universe is multi-asset. Violates Forward-First.
- **Hand-authored provider→broker symbol map** (in Trader or carried per-bundle):
  rejected. This is the artifact that rots; a stale row silently routes an order to the
  wrong listing/currency. It is precisely the maintenance burden we set out to avoid.
- **Author the Nautilus `InstrumentId` directly in the Book Config** (`IHYU.LSEETF`,
  `BTC/USD.PAXOS`): rejected as the default, **kept as a documented escape hatch**.
  Human-readable and dependency-free, but it is a hand-authored per-instrument identity,
  broker-coupled (the venue is baked into the id), and does not stay provider/broker
  independent or scale. Acceptable only for a tiny, static, single-venue book.
- **Security Master owned by Trader alone**: rejected. `aerd export` must resolve
  ticker→FIGI as well, so the mapping knowledge is shared. Placing it in `aegis-runtime`
  (the existing shared kernel) keeps one implementation, consistent between research-time
  tagging and live resolution.

## Consequences

- **`DataContract` change (RD coordination).** The bundle's `DataContract` carries a FIGI
  per instrument and the weight frame is keyed by FIGI rather than provider ticker. This
  is a dedicated change against `aegis-rd-qcj`/#40. The provider ticker stays in the RD
  config for *data fetch only* and never crosses the boundary.
- **OpenFIGI dependency at two points.** `aerd export` (ticker→FIGI, resolved once and
  baked — auditable, frozen, content-addressed with the rest of the bundle) and Trader
  boot (FIGI→contract metadata). Resolution is **fail-closed**: an ambiguous or
  unresolvable FIGI stops the export or stops the book at boot; a guess never trades.
- **Security Master is a deep module in `aegis-runtime`** with a narrow interface
  (`FIGI → resolved venue contract`, and the inverse for the netting↔diff bijection). It
  hides OpenFIGI, the exchange-code translation, and the Nautilus `InstrumentProvider`
  behind one boundary.
- **One bounded residual table:** Bloomberg exchange code → IBKR exchange (a few dozen
  stable entries), living in the venue adapter — not a per-instrument universe. A new
  instrument on a known exchange needs zero edits; a new *exchange* needs one line.
- **Two identities, one bijection.** Netting identity = FIGI; position/diff/order identity
  = Nautilus `InstrumentId`. The Security Master resolves the bijection once at boot into a
  bimap, so `compute_weights` output (FIGI-keyed) nets in FIGI space and diffs against
  `portfolio.net_position(instrument_id)` without ambiguity.
- **Crypto caveat.** FIGI covers crypto via OpenFIGI, but coverage for a specific crypto
  venue/pair must be verified before that venue is enabled.
- **Forward-First.** A future non-IBKR venue adapter resolves the same FIGIs to its own
  contracts; the canonical identity and every existing bundle are unchanged.
