# Aegis Data

Shared historical market-data context for Aegis RD and Aegis Trader. It names
historical data by the same instrument identity that crosses the research/live
boundary, so sourcing and execution read from one vocabulary.

## Language

**Historical Store**:
The durable corpus of historical market data used by Aegis RD and Aegis Trader,
named by **InstrumentRef** rather than provider ticker. It contains native market
bars, not base-currency-transformed series; for a continuous exposure, the stored
identity is the **FuturesRef** that defines the exposure, not one dated contract.
_Avoid_: cache, ticker store, provider cache, symbol cache

**Native Market Bars**:
Historical OHLCV bars in the instrument's own quote currency, before any
base-currency conversion. They are the clean market-data substrate shared by
research evidence and Trader backtests.
_Avoid_: converted bars, base-currency bars, return inputs

**FX History**:
Historical exchange-rate series stored separately from instrument bars and
reused independently by research and Trader backtests. FX History supports
currency conversion and valuation; it is not instrument identity and does not
select its own provider.
_Avoid_: instrument bars, traded pair, per-run FX, inline conversion data

**Data Request**:
A neutral request for historical market data over one or more **InstrumentRefs**,
bounded by arrays, timeframe, and date window. It is independent of Aegis RD's
Run Config language.
_Avoid_: DataConfig, run data config, provider request

**Provider Locator**:
A provider-specific address an adapter uses to fetch data for an **InstrumentRef**.
It is fetch input only; it is not instrument identity and can differ by source.
_Avoid_: identity, symbol, canonical ticker, InstrumentRef

**Historical Provider**:
A remote market-data source that can supply historical bars for the
**Historical Store**.
_Avoid_: CSV, synthetic data, local fixture, cache backend

**Dataset**:
The named market-data universe selected inside a **Historical Provider** for a
historical request. A Dataset scopes where provider source material is drawn
from; it is request semantics, not provider kwargs.
_Avoid_: provider, ticker, root, provider kwargs

**Gap-Fill Provider**:
The **Historical Provider** selected by Aegis RD when it uses the shared
**Historical Store** path. It is consulted only when **Ensure Coverage** finds a
**Gap**; it is declared once for the whole data request and is not part of
historical-data identity.
_Avoid_: store key, identity, Trader provider, FX provider, always-fetch source

**Pull**:
The act of sourcing historical market data from a provider and materialising it
into the **Historical Store** under its **InstrumentRef** identity. A Pull is
additive: existing covered history is reused, and only uncovered parts of the
requested window need provider sourcing.
_Avoid_: read, load, hydrate implicitly, fetch all

**Ensure Coverage**:
The store-backed operation that satisfies a **Data Request** by reading existing
**Covered History** and performing **Pulls** only for missing **Gaps**. Ensure
Coverage may call the configured **Gap-Fill Provider** and write the
**Historical Store**; it is the Aegis RD cache path, not the read-only Trader
path.
_Avoid_: Store Read, full-range repull, live-only load, unchecked cache miss

**Store Read**:
A read-only lookup in the **Historical Store** for complete coverage of a
requested window. A Store Read never contacts a provider; absent or incomplete
data is a closed failure. Aegis Trader backtests use Store Read.
_Avoid_: pull, fetch, load, cache miss fallback

**Gap**:
A missing expected bar for an **InstrumentRef**, timeframe, and requested window,
according to that instrument's trading calendar. Weekends, exchange holidays,
and non-session periods are not gaps.
_Avoid_: calendar day hole, business-day hole, missing parquet file

**Covered History**:
The subset of the **Historical Store** that has passed store-admission checks for
the requested arrays and timeframe. Data with gaps or missing required arrays is
not covered history, even if a provider returned rows for part of the window.
_Avoid_: raw provider result, partial cache, degraded coverage

**Raw Futures Leg**:
The native market bars for one dated futures contract supplied by a
**Historical Provider**. Raw Futures Legs are source material for continuous
futures history and are retained independently of any roll rule or adjustment.
_Avoid_: continuous future, FuturesRef, adjusted series, generic contract

**Fetch Ledger**:
The record of half-open time windows over which a **Raw Futures Leg** has been
requested from a **Historical Provider**, independent of how many bars came
back. A fetched window — including a legitimately empty one — counts as covered,
so a thin contract is never re-requested forever; it is fetch bookkeeping, not
**Covered History**.
_Avoid_: bar coverage, Covered History, observed-bar completeness, gap marker, fabricated coverage

**Continuous Futures History**:
Covered history for a **FuturesRef**, derived from **Raw Futures Legs** by its
roll rule and adjustment method. It is reusable derived history, not the provider
source material itself.
_Avoid_: raw contract bars, dated contract, provider result

**Liquid Cycle**:
The subset of a futures root's dated contracts that a **Continuous Futures
History** actually holds and rolls through: those that are ever the **Liquidity
Leader** over their own life. The roll schedule and back-adjustment see only the
Liquid Cycle, never the full listed curve. Membership is read from data, not a
per-product month cycle.
_Avoid_: front month, active month, all listed contracts, even-month cycle

**Liquidity Leader**:
The live dated contract of a root carrying the most trading volume — the contract
the market is actually trading. Being the Liquidity Leader at some point in its life
is what admits a contract to the **Liquid Cycle**; how the volume is measured is a
sourcing choice, not part of the term.
_Avoid_: nearest contract, front month, highest open interest (as identity)

**Serial Month**:
A dated contract that is never the **Liquidity Leader** in its own life (e.g.
COMEX gold's odd-month K/N contracts). A Serial Month is excluded from the
**Liquid Cycle**, so it places no roll seam and contributes no prices; excluding
it drops no exposure, because the liquid contract covering that calendar month
trades every session.
_Avoid_: thin contract, illiquid leg, off-cycle month, serial future

**Listed Adjustment Policy**:
The explicit price-adjustment choice for listed-instrument history, such as raw
OHLCV with a separate Adj Close array when requested. It is part of what makes a
listed Store Read reproducible.
_Avoid_: provider default, implicit auto-adjust, adjusted Close ambiguity
