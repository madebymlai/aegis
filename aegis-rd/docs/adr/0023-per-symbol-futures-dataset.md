# Futures Dataset is per-symbol, with no block default

Status: superseded (the per-symbol `dataset` attribute was removed).

> **Superseded.** Futures are now declared as bare `RootSymbol` strings in `data.futures`
> (`configuration/field_types.py`, `configuration/schema.py:119`); there is no `SymbolSpec`,
> no per-symbol `dataset` field, and no `FuturesRef` type. Cross-boundary identity is the
> Nautilus `InstrumentId` (root ADR-0007); a continuous-future root materializes as
> `{root}.{venue}` (e.g. `ES.XCME`), and the Dataset / Gap-Fill Provider is no longer a
> per-symbol identity attribute. The text below is retained as the rationale at the time it
> was accepted.

Futures `SymbolSpec.dataset` is the single home for the Databento Dataset that
becomes `FuturesRef.dataset`. `DataConfig` has no `dataset` field, and a futures
symbol without `dataset` is invalid. Listed symbols still forbid `dataset`.

This deliberately rejects the block-default-plus-per-symbol-override design. A
default would make the authoring surface shorter for all-GLBX universes, but it
would reintroduce the exact ambiguity this decision removes: the `store` path,
direct `bento` path, and Execution Bundle export would all need a resolver and
would have to decide what happens when a symbol and the block disagree. The
slightly repeated `dataset: GLBX.MDP3` on CME roots is cheaper than carrying two
levels of truth.

The practical driver is mixed-Dataset futures universes. Atalanta's live
long/short futures sleeve needs CME Globex roots (`GLBX.MDP3`) beside ICE roots
(`IFUS.IMPACT` and `IFEU.IMPACT`) in one `store` data block. The Historical Store
already partitions futures history by Dataset before root, and the Execution
Bundle already crosses the RD-to-Trader boundary as `FuturesRef`, so the correct
shape is to put the Dataset directly on each futures symbol and flow it through
unchanged.

## Consequences

- `data.provider` remains block-level: a `store` block still has one Gap-Fill
  Provider, and this change does not permit mixed listed/futures provider
  blocks.
- Futures-root uniqueness remains by `root`, not `(dataset, root)`, because RD
  Symbol Name and panel columns are the root.
- Store loading and Execution Bundle export read `symbol.dataset` directly, with
  no fallback resolver.
- Existing all-GLBX configs migrate by stamping `dataset: GLBX.MDP3` onto each
  active root and pinning the new config schema version.
- Activating ICE roots is separate operational work, gated on a live Databento
  subscription check for `IFUS.IMPACT` / `IFEU.IMPACT`.
