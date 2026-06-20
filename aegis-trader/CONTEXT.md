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
Bundle**. Its signed target weights are scaled by the Trader-owned **Allocator** and
summed with the other sleeves into the book's net target. A sleeve owns no account; it
exists only in Aegis Trader's bookkeeping.
_Avoid_: strategy, fund, sub-account, allocation

**Risk Share**:
The static share of the **Commingled Book's** volatility budget assigned to a **Sleeve**.
The **Allocator** converts Risk Shares, sleeve target weights, and realized sleeve
volatility estimates into the capital multipliers netted by the rebalancer.
_Avoid_: capital budget, weight, sizing

**Risk Group**:
The top-level role of a **Sleeve** in the book's risk budget: Floor, Target, or
Expansion.
_Avoid_: strategy class, sector, asset class

**Allocator**:
The Trader-owned domain service that scales raw per-sleeve target weights into
risk-budgeted target weights before the sleeves are netted into one target-weight
vector.
_Avoid_: alpha model, bundle allocator, portfolio optimizer

**Book Config**:
The Aegis Trader-owned, declarative specification that fully defines the **Commingled
Book**: each **Sleeve** (a name/risk group bound to an **Execution Bundle** by its
content-addressed wheel filename), its **Risk Share**, the book volatility target,
exposure caps, and drift bands. Inert — it selects trusted artifacts and parameters
only; it is the live counterpart of Aegis RD's **Run Config**.
_Avoid_: book manifest, manifest, portfolio config, roster

**Backtest Timeframe**:
The single bar timeframe a Trader backtest runs for all installed **Sleeves** in
one **Commingled Book**. A backtest with mixed bundle timeframes is a closed
failure, not a multi-timeframe simulation.
_Avoid_: per-sleeve timeframe, mixed cadence backtest, implicit resampling

**Security Master**:
The resolution of an **InstrumentRef** to its live, tradable venue contract — a
*responsibility fulfilled by vendor-native services, not a bespoke Aegis module* (ADR-0005).
A **ListedRef** is resolved by handing its **FIGI** to Interactive Brokers'
`InstrumentProvider` (`secIdType='FIGI'` + `convert_exchange_to_mic_venue`), which returns the
qualified listing and MIC venue. A **FuturesRef** is resolved at **IBKR** (live/paper is
IBKR-only, on a delayed subscription): the **roll rule** picks the front dated contract, qualified
by its exchange-native Globex `localSymbol` — never IB `CONTFUT`. **Databento** and **yfinance**
are research-only substrates (`dataset` is a research tag, not in the live loop). Resolution is
fail-closed, and a **Roll** is detected when the roll rule advances the front contract. The
cross-context *identity* (the **InstrumentRef**) is still single and authoritative; only its
*resolution* is vendor-native.
_Avoid_: symbol map, instrument map, ticker table, security database, FIGI resolver, VenueContract (resolution is vendor-native — no bespoke resolver or intermediate contract type)

Add domain terms here as decisions crystallise — one or two sentences each,
defining what the term **is** (not what it does), with an `_Avoid_:` line
listing rejected synonyms. Keep this file a glossary only; implementation
detail belongs in `docs/adr/`, not here.
