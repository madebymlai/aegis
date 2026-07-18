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

**Market-Data Stream**:
One instrument consumed at one bar timeframe — the pure-domain mirror of a
Nautilus `BarType` subscription. Each **Sleeve** trades at its own **Execution
Bundle** cadence: Book assembly derives every Sleeve's required streams and
exposes the deduplicated Book union, and the runtime subscribes, warms, loads,
and reads each stream independently. A Sleeve recomputes only on its own
completed period; the whole **Commingled Book** is still allocated and netted
centrally on every due update. Missing required data fails or holds explicitly.
_Avoid_: backtest timeframe, book-wide timeframe, implicit resampling

**Analytics Horizon**:
The **Commingled Book**'s one bucketing-and-annualization fact: how observation
timestamps group into return rows (`bucket_of`, epoch-floor with the weekend
fold under the weekday convention) and how many rows a year holds. Derived at
Book assembly from the roster's declared **Sleeve** cadences — width is the
slowest cadence floored at one day; the count comes from an internal
convention table (1D→252, 1W→52) — never from operator config and never from
data. Consumers (the Sleeve Ledger and performance reporting) receive it as a
required parameter; trading cadence stays per-Sleeve and untouched.
_Avoid_: annualization config, inferred horizon, per-sleeve horizon

**Security Master**:
The resolution of an **InstrumentId** to its live, tradable venue contract — a
*responsibility fulfilled by vendor-native services, not a bespoke Aegis module* (ADR-0005, root ADR-0007).
An instrument is resolved by handing its declared `InstrumentId` to Interactive Brokers'
`InstrumentProvider` (`load_ids` + `convert_exchange_to_mic_venue`), which returns the
qualified listing and MIC venue (`CME → XCME`). Live/paper is **IBKR-only**, on a delayed
subscription. A continuous future is declared as a bare **root**; its live front leg is chosen by
causal, volume-based liquidity detection, and a **Roll** is detected when that front advances —
keyed by `InstrumentId`, with no declarative roll calendar. **Databento** and **yfinance** are
research-only substrates, never in the live loop. Resolution is fail-closed. The cross-context
*identity* is the single, authoritative **InstrumentId**; only its *resolution* is vendor-native.
_Avoid_: symbol map, instrument map, ticker table, security database, FIGI, FIGI resolver, VenueContract, InstrumentRef (resolution is vendor-native — no bespoke resolver or intermediate contract type)

**Roll**:
The advance of a continuous future's front leg from one dated contract to the next — detected
causally at bar time when the newer leg overtakes the current front on observed volume, keyed by
the `(from, to)` `InstrumentId` pair. It re-bases the back-adjusted continuous series across the
seam so the series stays continuous, and uses no declarative roll calendar — the front is chosen
live from volume, so live and research pick the same leg.
_Avoid_: roll calendar, roll rule, rollover schedule, contract switch, expiry roll

**Roll Desk**:
The single authority for the **Commingled Book's** live continuous-future exposure — it owns
each declared root's back-adjusted continuous series and the dated front leg the root currently
resolves to, re-based across every **Roll** so live stays identical to research. One per book;
the continuous series is read, and a continuous root's execution front is resolved, only through it.
_Avoid_: roll manager, roll engine, feeds orchestrator, continuous feed manager, continuous service, roll handler

**Startup Fast-Forward**:
The bounded future-in-past replay that restores a **Commingled Book** from its required market
history through the live-start boundary, using the same causal state transitions as live trading
but producing no historical orders; it is complete only when all required history is folded and
the book is ready to reconcile and trade.
_Avoid_: checkpoint restore, warmup, backfill, historical trading

**Broker Connection**:
The environment-resolved IBKR connection (`IBConnectionSettings`: host, port, client
id, account id) that a live trader run trades through. Paper and live are **not** run
modes — they are the *same* code path pointed at different gateway ports, so the **port
alone** distinguishes paper from live; the system requires `IB_PORT` and `account_id`
explicitly and fails closed rather than assume which gateway it is talking to. Read from
the process environment (never the committed **Book Config**) and handed to the single
IBKR adapter, which translates it into Nautilus's stock client configs. There is no
`--mode`: the operator-facing surface is `aegis-trader backtest` (offline) and
`aegis-trader trader start`/`stop` (live; the port decides paper vs live).
_Avoid_: mode, paper mode, live mode, run mode, environment, broker config, gateway profile

Add domain terms here as decisions crystallise — one or two sentences each,
defining what the term **is** (not what it does), with an `_Avoid_:` line
listing rejected synonyms. Keep this file a glossary only; implementation
detail belongs in `docs/adr/`, not here.
