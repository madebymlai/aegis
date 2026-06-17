# Make cross-boundary instrument identity asset-agnostic via `InstrumentRef`, resolved as-of, with a roll step

Status: accepted (design; implementation pending). Refines ADR-0002 (FIGI / Security Master)
before its own implementation; extends Aegis Trader ADR-0003 (deep modules) with a second
order source. Depends on the `aegis-runtime` `DataContract`.

ADR-0002 made the **FIGI** the sole cross-boundary instrument identity, resolved once at boot
into a static `FIGI → InstrumentId` bimap, with the overlay netting "in canonical FIGI space".
That is equity-shaped and breaks for futures at every hop: a continuous futures exposure has
**no FIGI**; the venue table has **no futures venues**; resolution is **static** (no roll); and a
future's broker contract is **per dated contract**, so it changes over the life of one position.

We refine the identity model to be asset-agnostic:

1. **`InstrumentRef` replaces the bare FIGI as the canonical cross-boundary identity** — a closed
   variant type (`aegis-runtime`): `ListedRef(figi)` for permanently-listed instruments, and
   `FuturesRef(root, dataset, roll_rule, adjustment)` for a *continuous* futures exposure. FIGI is
   demoted from "the universe" to the `ListedRef` variant; the cash-equity/ETF path is unchanged.
2. **The `DataContract` carries `refs: tuple[InstrumentRef, …]`** (not `figis: tuple[str, …]`), and
   the signed target-weight frame is keyed by `InstrumentRef`. The domain nets in **InstrumentRef
   space**; the dated contract a `FuturesRef` stands for is *internal execution detail* that never
   crosses as identity (the same status `symbols`/`currency` already have).
3. **The Security Master resolves as-of a date:** `resolve(ref, as_of) → InstrumentId`. A
   `ListedRef` resolves date-invariantly (the boot bimap of ADR-0002 still holds); a `FuturesRef`
   applies its roll rule to `as_of` to pick the live dated contract, then resolves *that* to an
   `InstrumentId` / IBKR `conId`. The inverse map folds a realized dated-contract position back to
   its `InstrumentRef` so the rebalancer reasons in continuous space.
4. **The roll step is a second, band-exempt order source.** Because the rebalancer sees
   realized == target across a roll (continuous netting), it emits nothing for it; so a **Roll** —
   detected when `resolve(ref, today)` differs from the held contract — is produced at the execution
   edge as an *exposure-neutral* `OrderIntent` pair that **bypasses the drift band** (a roll is
   mandatory, not optional) but **passes the risk caps + kill-switch** and is labelled distinctly in
   observability. For a `ListedRef` resolution is date-invariant, so the step is a structural no-op;
   only a `FuturesRef` ever rolls. No asset-class branching outside the Security Master's sealed
   per-variant resolution.

## Considered options

- **Keep FIGI as the sole identity; pin a generic-future FIGI per root** (the ADR-0002 escape
  hatch): rejected. A static FIGI cannot name a *rolling* exposure, the OpenFIGI resolver and the
  Bloomberg-exchange→MIC table are equity-only, and a pinned generic still does not tell the broker
  which dated contract to trade today. It satisfies the machinery and resolves nothing.
- **Net in dated-contract space** (the rebalancer sees `CLF5`, emits the roll itself): rejected. It
  drags the roll calendar and dated contracts into `domain/rebalancer.py` — the high test seam that
  Aegis Trader ADR-0003 keeps Nautilus-free and broker-free — and it breaks the `DataContract`'s
  stable identity, since a weight frame keyed by a contract that changes over time has no durable key.
- **One `OrderIntent` producer** (fold the roll into the rebalancer): rejected. To make the
  pure rebalancer emit rolls you must feed it dated-contract realized weights or a special
  roll input — either way the high seam is corrupted, and it couples *alpha/drift* (changes
  when sizing/bands change) to *maintenance/roll* (changes when roll rules/venues change), two
  responsibilities with different change drivers.
- **Hide the roll inside execution-port resolution** (silently substitute the contract on
  submit): rejected. It removes mandatory trades from observability and the risk caps — a guess that
  trades unaudited, against the evidence/provenance ethos.
- **ISIN / dated contract as the key**: still rejected (ADR-0002): securities-only, and a dated
  contract is not durable across the roll.

## Consequences

- **`DataContract` change (RD + runtime coordination).** `figis` becomes `refs`; the weight frame is
  `InstrumentRef`-keyed. `aerd export` emits a `ListedRef` for a cash listing (byte-identical to
  today's FIGI path) and a `FuturesRef` for a futures candidate. Provider ticker stays RD-internal.
- **Security Master deepens by one parameter.** The interface widens from `resolve(figi)` to
  `resolve(ref, as_of)`; the implementation absorbs the roll calendar, the live-contract pick, the
  futures-venue table rows (e.g. `GLBX→XCME`), and the dated-contract→ref inverse. The interface
  grows by one date; the implementation grows a lot — it stays a **deep module** (CONTEXT.md's
  "single authority for cross-context instrument identity").
- **`domain/` is unchanged by adding an asset class (OCP).** The rebalancer's interface does not
  move; it never learns what a contract or a roll is. Aegis Trader ADR-0003's Nautilus-free
  high seam is preserved.
- **conId stays inside the Nautilus IBKR adapter.** `as_of` is a domain date; broker resolution
  remains the one isolated IBKR seam. A second venue is a new resolver impl, not a domain change.
- **Two order sources compose at the execution port.** The roll step runs first (normalise held
  positions onto current contracts), then drift applies — so a future that rolls *and* drifts in one
  cycle yields one coherent order set, netted in resolved-contract space.
- **Two cadences, not just two producers.** The roll step runs on the **base tick**, not on
  a sleeve's alpha `BarType` (bar-length agnostic), so a coarse alpha cadence can never carry a
  position into expiry. It re-resolves `resolve(ref, as_of=now)` for every held ref each tick and is
  **idempotent** — a structural no-op until an actual roll, so per-tick checking is cheap.
  This refines ADR-0001 (per-sleeve cadence + next-close): the sleeve bar drives *drift*; the base tick
  drives *the roll*. `as_of=now` reads the `TestClock`/`LiveClock`, so it runs identically across
  backtest/paper/live. Correctness constraint: the roll rule must pick a roll date with lead ≥ (tick
  cadence + next-close execution latency).
- **No primitive obsession.** Identity is a variant value type, not a string; the unbuilt
  `InstrumentRef` that Aegis Trader ADR-0003 referenced is now the real thing.
- **Forward-First.** A new asset class is a new `InstrumentRef` variant plus its resolution; existing
  bundles and the `ListedRef` path are untouched. (Crypto, already a FIGI caveat in ADR-0002, fits as
  a future variant.)
- **Execution precondition.** Live futures trades require a futures-capable account (not the UCITS
  wrapper); the roll step only ever fires real orders where the account permits them.
- **Deferred.** `FuturesRef`'s exact `roll_rule` representation, and whether `RollRule` becomes an
  internal seam of the Security Master (only once a second roll rule exists), are left to
  implementation.
