# aegis-runtime

Shared runtime (shared kernel) that executes one Locked **Candidate** and owns
the **cross-context instrument identity** vocabulary — both Aegis RD and every
**Execution Bundle** net and resolve against it, so research, export, and live
execution agree on which instrument a target weight refers to.

See the [Context Map](../CONTEXT-MAP.md) for how this kernel relates to Aegis RD
and Aegis Trader. This file is a glossary only; implementation detail belongs in
each context's `docs/adr/`.

## Language

**InstrumentRef**:
The canonical, asset-agnostic cross-boundary instrument identity: a closed
variant type whose cases are a **ListedRef** or a **FuturesRef**. It is what a
**DataContract**'s signed target-weight frame is keyed by, what the domain nets
in, and what the **Security Master** resolves to a venue-native contract. It
refines root ADR-0002: **FIGI** is no longer the sole identity but one variant
(`ListedRef`), so the identity is asset-agnostic rather than equity-shaped.
_Avoid_: FIGI (now only the ListedRef variant), symbol, ticker, instrument id, security

**ListedRef**:
The **InstrumentRef** variant for a permanently-listed instrument (cash equity,
ETF/ETC), identified by its **FIGI**. Resolution is *date-invariant* — the same
FIGI names the same tradable instrument forever — a `ListedRef` never rolls.
_Avoid_: equity, stock, cash instrument, the FIGI

**FuturesRef**:
The **InstrumentRef** variant for a futures position, identified by its contract
**root** and **roll rule** — not a single contract. It names a *continuous*
exposure; the live dated contract it stands for at any moment is internal
execution detail the **Security Master** resolves *as-of* a date. The continuous
exposure is the identity that crosses the boundary and that the domain nets in;
the dated contract never crosses as identity.
_Avoid_: contract, continuous contract, the future, dated contract, generic

**Roll**:
The trade that moves a futures position from the contract it currently holds to
the next, detected when the contract the **Security Master** resolves *today*
differs from the one held (only a **FuturesRef** rolls; a **ListedRef** resolves
date-invariantly). A roll is *mandatory* and *exposure-neutral* — the
**InstrumentRef** and its target weight are unchanged, only the live dated contract
underneath moves — so it bypasses the drift band but still passes the
risk caps.
_Avoid_: migration, reconcile (that is position reconciliation against the broker), rebalance, rollover

**MarketDataBundle**:
The eager value object a **Component** reads prices from: a mapping of materialised
**Array** panels (see [Array](../aegis-rd/CONTEXT.md)) with one guarded accessor,
`bundle.array(name)`, that fails loud on a dict miss (`"...was not supplied"`). Dict
membership is the sole guard — an Array is loaded iff it is a key. It is the *single*
canonical Array type across the research↔execution seam (root ADR-0006): a Component sees
the same Bundle whether it runs under a research **Run** or inside an **Execution Bundle**.
Distinct from `MarketDataResult`, the research-side pre-validation loader output that holds
no Array access until it passes its usability gate.
_Avoid_: feature bundle, price bundle, the dict, MarketDataResult (that is the pre-gate loader type)
