# Instrument identity is the Nautilus `InstrumentId`, authored in the Execution Bundle and resolved IBKR-native

Status: accepted (implemented). **Supersedes ADR-0002** (FIGI / Security Master),
**ADR-0003** (asset-agnostic `InstrumentRef`), and **ADR-0004** (InstrumentRef-keyed
historical store) — all three were design-only, "implementation pending", and never
built. **Refines ADR-0005**: its surviving decision (resolve vendor-natively through
IBKR's `InstrumentProvider`, build no bespoke resolver) stands, but the identity it
resolves is the `InstrumentId`, not a FIGI or `InstrumentRef`.

The cross-context **identity** is the Nautilus `InstrumentId` (`{symbol}.{venue}`, e.g.
`IDTL.LSEETF`, `ES.XCME`), authored directly in the **Execution Bundle** and carried as
the column key of the signed target-weight frame. There is no separate identity layer:
no canonical FIGI hub, no `InstrumentRef`/`ListedRef`/`FuturesRef` variant type, no
bespoke **Security Master**, no `VenueContract`. The escape hatch ADR-0002 documented and
rejected — "author the Nautilus `InstrumentId` directly in the Book Config" — quietly
became the design, because a `{symbol}.{venue}` id is already broker-resolvable and the
FIGI/`InstrumentRef` indirection never acquired a live consumer.

How it actually works:

1. **Authored in the bundle.** `DataContract.instrument_ids: tuple[InstrumentId, …]`
   (`aegis-runtime/aegis_runtime/bundle.py`) is the declared source of truth; it is
   serialized as `instrument_id.value` and reloaded with `InstrumentId.from_str`
   (`aegis_runtime/bundle_loader.py`). The weight/price frames are keyed by `InstrumentId`.
2. **Live/paper resolution is IBKR-native and direct.** At boot,
   `union_native_instrument_ids(sleeves)` (`aegis-trader/aegis_trader/bundles/book_sleeves.py`)
   collects the declared ids across all sleeves and hands them straight to IBKR's
   `InteractiveBrokersInstrumentProviderConfig.load_ids` (`aegis-trader/.../trader/node.py`,
   `aegis-data/aegis_data/ibkr.py`). `convert_exchange_to_mic_venue=True` qualifies IBKR
   exchanges to their MIC venues (`CME → XCME`, `NYBOT → IFUS`). There is **no** FIGI
   handoff (`secIdType='FIGI'`), **no** OpenFIGI client, and **no** hand-maintained
   symbol map.
3. **Backtest builds the same ids locally** from the bundle's declared `InstrumentId`s /
   catalog definitions — resolution-via-IB is a live-boot concern only.
4. **Futures are a bare root plus a continuous `InstrumentId`.** A root (e.g. `ES`) in
   `DataContract.futures` materializes a synthetic continuous id (`ES.XCME`); the live
   Roll Desk drives `aegis-data`'s `ContinuousContractModel` to expose the current front
   leg at bar time. A **Roll** re-bases the continuous series under the bundle contract's
   declared adjustment mode (`BACKWARD_RATIO` or `BACKWARD_SPREAD` — ADR-0009) and is
   keyed by the `(from, to)` `InstrumentId` pair — there is no declarative roll calendar,
   `roll_rule`, or `FuturesRef.dataset` in the live loop.
5. **The strategy resolves nothing at runtime.** "Identity is the native `InstrumentId`
   declared by each Execution Bundle; the strategy never resolves symbols, FIGIs, or
   broker-specific aliases at runtime" (`aegis-trader/.../trader/strategy.py`).

## Considered options

- **FIGI as the canonical identity behind a Security Master** (ADR-0002): rejected /
  withdrawn. The bespoke resolver, OpenFIGI client, and Bloomberg-exchange→MIC table were
  never built (ADR-0005 already withdrew them), and a Nautilus `InstrumentId` is already
  `{symbol}.{venue}` that IBKR's `InstrumentProvider` resolves directly. The FIGI hub added
  an identity indirection and a netting↔execution bijection that no live code consumed.
- **An `InstrumentRef` variant type for asset-agnosticism** (ADR-0003) **and an
  InstrumentRef-keyed historical store** (ADR-0004): rejected. The variant type was never
  implemented. Futures asset-agnosticism is achieved without a new identity type — a bare
  root, a synthetic continuous `InstrumentId`, and a live causal roll — so the domain, the
  bundle, and the store all stay on the single `InstrumentId` key. A continuous futures
  exposure *does* have an id (`ES.XCME`); it just is not a dated contract.
- **Hand-authored provider→broker symbol map**: still rejected (as in ADR-0002). The
  `InstrumentId` is the durable, broker-resolvable key; no per-instrument map is maintained.
- **ISIN / dated contract as the key**: still rejected. Securities-only, and a dated
  contract is not durable across a roll — the continuous `InstrumentId` is.

## Consequences

- **One identity type end to end.** Research authoring, the bundle `DataContract`, the
  rebalancer's netting, and execution all key on the Nautilus `InstrumentId`; no
  netting-identity ↔ execution-identity bimap is built (the ADR-0002 "two identities, one
  bijection" consequence is withdrawn).
- **No primitive obsession.** `InstrumentId` is a real Nautilus value type, parsed and
  validated via `InstrumentId.from_str` and checked when a bundle is loaded — not a bare
  string the domain reinterprets.
- **Venue lives inside the identity.** Each `InstrumentId` carries its own venue, so
  identity is never reconstructed by string-joining a symbol to a book-wide venue — the
  property aegis-trader ADR-0002 protects.
- **Resolution is vendor-native (ADR-0005 stands).** IBKR's `InstrumentProvider.load_ids`
  resolves both equities and futures; the only residual is Nautilus's maintained
  exchange→MIC mapping plus a tiny override set — one line per *exchange*, zero per
  *instrument*.
- **Futures continuity is live and data-layer-owned, not declarative.** It is driven by
  the Roll Desk over `ContinuousContractModel` (volume-led front selection), keyed by
  `InstrumentId` pairs. The re-basing *algebra*, by contrast, is contract-declared, not
  data-owned: each root materialises under the adjustment mode its locked Run recorded
  (ADR-0009 refines this ADR). Per-symbol *research* dataset selection survives on the
  research side (see `aegis-rd` ADR-0023) but is a data-fetch input, never an identity
  attribute.
- **Forward-First.** A new asset class is a new `InstrumentId` `{symbol}.{venue}` plus its
  IBKR resolution, not a new identity type; existing bundles are unchanged.
- **FIGI is retired as an identity term.** It is no longer the cross-boundary identity,
  the bundle key, or a resolution input. A research export may still look a ticker up
  through OpenFIGI as one way to discover the correct listing, but what crosses the
  boundary is the resolved `InstrumentId`; FIGI otherwise survives only as opaque strings
  in test fixtures and as historical references in superseded ADRs.
