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

**Commingled Book**:
The single live account whose positions are the net of every **Sleeve's** target
allocation. One account holds all sleeves' instruments directly; the sleeves are
notional sub-portfolios within it, not separate legal funds or broker sub-accounts.
Monetising a spiked tail means trading the instruments directly, so the book is one
commingled account rather than a fund-of-funds with a subscription/redemption cycle.
_Avoid_: fund-of-funds, sub-account, master account, portfolio

**Sleeve**:
A notional sub-portfolio of the **Commingled Book** backed by exactly one **Execution
Bundle**. Its signed target weights are scaled by its **Sleeve Budget** and summed
with the other sleeves into the book's net target. A sleeve owns no account; it exists
only in Aegis Trader's bookkeeping.
_Avoid_: strategy, fund, sub-account, allocation

**Sleeve Budget**:
The fraction of the **Commingled Book's** capital notionally allocated to a **Sleeve**
— the scalar each sleeve's signed weights are multiplied by before the sleeves are
netted into one target-weight vector.
_Avoid_: weight, allocation, capital, sizing

Add domain terms here as decisions crystallise — one or two sentences each,
defining what the term **is** (not what it does), with an `_Avoid_:` line
listing rejected synonyms. Keep this file a glossary only; implementation
detail belongs in `docs/adr/`, not here.
