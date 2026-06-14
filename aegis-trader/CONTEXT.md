# Aegis Trader

Live execution context for Aegis: takes strategies promoted by **Aegis RD**
(see the [Context Map](../CONTEXT-MAP.md)) and trades them against real venues.

## Language

**Execution Bundle**:
A versioned, installable wheel that packages one **Candidate** for live trading —
the strategy, its wired indicators, and the parameters a **Lock** resolved, baked
in — as a self-contained unit with no **Candidate Store** dependency at runtime.
Aegis RD's `aerd export` produces it from a Lock; Aegis Trader installs it and runs
it through the shared **`aegis-runtime`** package, feeding it market data to get a
signed target-weight frame back.
_Avoid_: run config bundle, strategy bundle, Nuitka bundle, promotion, package

Add domain terms here as decisions crystallise — one or two sentences each,
defining what the term **is** (not what it does), with an `_Avoid_:` line
listing rejected synonyms. Keep this file a glossary only; implementation
detail belongs in `docs/adr/`, not here.
