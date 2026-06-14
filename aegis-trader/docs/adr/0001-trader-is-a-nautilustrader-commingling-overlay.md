# Aegis Trader is a NautilusTrader commingling overlay

Status: accepted (scaffolding pending; depends on the `aegis-runtime` carve-out
[`aegis-rd-qcj.1`] and ≥1 **Execution Bundle**; state/reconciliation and package
layout tracked separately)

Aegis Trader runs the live **Commingled Book** *as a NautilusTrader system*. Everything
from order-intent outward — the run loop, clock, market data, the `ExecutionEngine`/OMS,
`Portfolio`/`Account` (NAV), `Cache`, startup reconciliation against the broker, and the
Interactive Brokers connectivity — belongs to Nautilus. Aegis owns only the
*alpha-to-order-intent* layer: discover the **Sleeves** named in the **Book Config**,
call each backing **Execution Bundle's** `compute_weights` on its own latest bar, scale
by **Sleeve Budget**, **net signed weights per instrument**, validate the netted book
against the Book Config's exposure caps, size against NAV, diff against current
positions, and submit orders. That overlay is a **pure module importing no Nautilus types**; a single Nautilus
`Strategy` (the rebalance adapter) drives it. The bundles are loaded *behind* the Nautilus
interface and *called* by the overlay — never registered as node strategies.

## Considered options

- **One Nautilus `Strategy` per sleeve** (each sleeve submits its own orders, Nautilus
  nets at the account): rejected. There is no single point where the combined book exists
  before orders go out, so the netted book can never be validated against the book caps; sleeves
  sharing an instrument pay the spread twice on the crossing quantity; and each sleeve
  sizes against the shared NAV independently, double-counting capital. The invariant
  "book-level risk lives in Trader, on the netted vector" becomes unenforceable.
- **Hand-roll execution, position/account state, and reconciliation** (the originating
  handoff §2): rejected. Re-implements a production-grade OMS, order lifecycle, partial
  fills, and broker reconciliation against real money, when Nautilus already provides them.
- **HEDGING OMS / one Nautilus position per sleeve**: rejected. Sleeves are *notional*
  sub-portfolios; the venue holds exactly one net position per instrument. NETTING matches
  the single Commingled Book, and per-sleeve P&L is synthetic Trader bookkeeping
  (weights × book returns), not venue positions.
- **Global synchronised as-of across sleeves** (rebalance only on the LSE∩Xetra
  intersection calendar): rejected. It freezes out trimming the `VOOL.DE` (Xetra) tail on
  a UK bank holiday — i.e. exactly the monetisation the book exists for. Instead each
  sleeve computes on its own most-recent completed bar; a sleeve whose venue is shut simply
  holds (multi-day-hold), and orders are emitted only for instruments whose venue is open.
- **Bundle loads its own market data**: rejected. It breaks the single consistent
  snapshot, opens N broker/data connections, and destroys the bundle's purity (no I/O, no
  cadence) that makes it content-addressed and testable. Trader feeds data in; the bundle
  stays a pure `data → signed weights` function.
- **Dynamic sleeve weighting computed live in Trader**: rejected. Conditioning allocations
  on market state is alpha and must carry **Provenance**; it belongs in Aegis RD as a
  composite **Strategy** exported as one Execution Bundle. Trader's budgets are static.

## Consequences

- **Dependencies:** Aegis Trader depends on `aegis-runtime`, `nautilus_trader`, and
  `pydantic`. **VBT PRO is a *transitive* dependency** — it arrives only when a bundle wheel
  (which declares it) is installed; Trader's own code is numpy/pandas/Nautilus/pydantic.
  Trader's path cannot be fully exercised until `aegis-runtime` and ≥1 bundle exist.
- **Single overlay `Strategy`, NETTING OMS.** One net position per instrument; sleeves are
  notional; sleeve P&L is synthetic.
- **The Book Config is the Trader-owned book definition.** It declares each sleeve
  (name/role → the bundle's **content-addressed wheel filename**, *not* a Lock reference),
  its Sleeve Budget, the exposure caps (per-sleeve and book), and the drift bands (ADR-0002).
  Binding by filename keeps the live book **decoupled from RD's research lineage** — the Lock
  is spent at export; provenance (`run_id`/`role`/`candidate_key`) is read from the bundle's
  own manifest at load, not carried in the Book Config. Only listed sleeves trade — this
  narrows root ADR-0001's "discover whatever is installed via the `aegis.execution_bundles`
  entry-point group" to explicit, fail-closed selection, with that group remaining the *load*
  interface for the selected wheel.
- **Instrument identity via the Security Master / FIGI** (root ADR-0002): the overlay nets
  in canonical FIGI space and resolves to a Nautilus `InstrumentId` at the execution edge.
- **Sizing is Trader's job.** Weights are dimensionless signed fractions (ADR-0007); the
  single capital base is the **account NAV in EUR** from the Nautilus `Portfolio`. FX and
  the GBp (pence) factor re-enter only at sizing, live from Nautilus, never from the bundle.
  Sleeve Budgets sum to a book gross defaulting `< 1.0`, configurable (leverage if raised).
- **Cadence is per-sleeve, timeframe-driven, event-driven** off bar-close at the sleeve's
  own `DataContract.timeframe`, debounced to one re-net per completed period. Daily is just
  the `1D` case. v1 wires the daily ETF venues (LSE + Xetra) only; a crypto/24-7 venue
  adapter is deferred until a crypto sleeve exists (the cadence model already generalises).
- **Execution is next-close** (decision from bar `t`'s close, fill at bar `t+1`'s close;
  research/VBT being re-pinned to `price="close"`, `from_ago=1`). Realised with a **one-bar
  execution lag** — the order submitted at `t+1` is sized from the target decided at `t` — so
  no look-ahead and live-realizable. **Backtest:** a plain `MARKET` order on the execution bar
  fills at that bar's close (proven by prototype; the `SimulatedExchange` rejects session TIFs
  — `AT_THE_OPEN` is denied, so `AT_THE_CLOSE` isn't used there). **Live (IBKR):** a `MARKET`
  with `TimeInForce.AT_THE_CLOSE` (Market-on-Close) → the closing auction (deepest liquidity,
  benchmark price). Both model the same fill point (the close), so research↔backtest↔live
  align — which **next-open could not**: a bar's open is unfillable in the Nautilus bar
  backtest and `AT_THE_OPEN` is rejected by the sim (proven). Trader mirrors research's
  non-executable mask as the calendar-aware "don't trade a closed/no-bar instrument" rule.
- **State leans on Nautilus; reconciliation is one deterministic rule per scope.** The
  reconciled `Cache` is the single source of truth for positions/orders/account/NAV — Trader
  keeps no parallel ledger. Nautilus's startup reconciliation always absorbs broker truth;
  Trader does not override it. No opt-in paths — two deterministic reactions: an
  **account-integrity failure** (NAV/cash mismatch beyond a band, wrong account id,
  cache-hydration failure) → **global halt** (no state is trustworthy); a **held instrument
  not in the current Manifest** → **quarantine + alert** (never auto-traded, but counted in
  the realized-book gate as real exposure, ADR-0002) while recognized sleeves keep
  rebalancing. Partial fills need no rule — reconciliation absorbs them. Trader-specific
  persistent state is only the Book Config (config) and a regenerable Security-Master
  resolution cache; per-sleeve P&L is *derived*, not a second ledger.
- **Forward-First:** new venues plug in as Nautilus adapters resolving the same FIGIs; the
  cadence and identity layers are unchanged.
