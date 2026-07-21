# Aegis RD

A research operating system for turning market hypotheses into reproducible, scored evidence.

## Language

**Run**:
A single, reproducible execution of a strategy hypothesis against market data, producing scored evidence and a manifest.
_Avoid_: research loop, experiment, backtest

**Component**:
A versioned, registered Python module that declares inputs, parameters, and outputs. Components come in two families: **Indicators** and **Strategies**.
_Avoid_: plugin, module, block

**Indicator**:
A **Component** that transforms market data **Arrays** into named numeric outputs consumed by **Strategies**.
_Avoid_: feature, signal, transform

**Strategy**:
A **Component** that consumes **Indicator** outputs and emits a single signed **target-weight** allocation frame — one weight per symbol per rebalance, where the sign is the **Direction** (positive = long, negative = short) and the magnitude is the intended share of capital.
_Avoid_: model, algorithm, alpha

**Array**:
A named market-data input series a **Run** loads — the OHLCV set (Open, High, Low, Close, Volume) plus any adjacent series a **Component** declares (e.g. Adj Close, Funding Rate). A Run's array contract declares which Arrays it requires; **Components** read them by name, distinct from an **Indicator** output computed from them.
_Avoid_: feature, panel, column, field

**Candidate**:
A scored parameter combination produced by an optimization **Run**. Each Candidate carries fixed parameters, complete-period **Metrics**, per-**Observation Block** Metrics, mean within-block rank, and provenance. Every Run publishes exactly three representative Candidates: best, median, and worst. These roles are chosen by regime-balanced mean rank over one continuous Development replay.
_Avoid_: trial, result, entry

**Invalid Candidate**:
A **Candidate** whose configuration is unworkable: an **Indicator** output is entirely non-finite over the full series because its lookback exceeds all available history. Detected before scoring, independent of the finite cash-holding score it would otherwise simulate to; misconfigured rather than merely poor. Every Invalid Candidate is also **Degenerate**.
_Avoid_: broken candidate, bad candidate, error

**Degenerate Candidate**:
A **Candidate** that cannot represent the **Candidate Grid**, excluded for one of three reasons: it is misconfigured (an **Invalid Candidate**), it earned no finite ranking score (non-trading), or it traded too few times to be trusted (under-traded). Non-trading is the absence of a finite ranking score — not merely zero trades: an Invalid cash-holder takes zero trades yet scores a finite 0.0 and is reported as **Invalid**, its more specific cause. Invalid is decided before scoring, the other two from results after; **Invalid Candidates** are the misconfigured subset.
_Avoid_: failed candidate, junk candidate, outlier

**Development Period**:
The single scored interval shared by every materialized **Candidate**, beginning after the common **Warmup** and ending at the Run's final data row. Candidate allocations and portfolio state evolve continuously across this interval; there is no terminal held-out phase or fresh validation Portfolio.
_Avoid_: train set, selection set, in-sample split

**Warmup**:
The unscored history needed to compute every selected **Component** for every materialized **Candidate**. A **Run** derives one common Warmup from the maximum resolved Component lookback, records its drivers in **Evidence**, and begins every Candidate's Development Period at the same row.
_Avoid_: burn-in config, training period

**Continuous Future-in-Past Replay**:
The causal simulation of each fixed **Candidate** exactly once across its entire **Development Period**. Decisions use only information available at that historical point, while positions, cash, costs, and portfolio state persist across later observational boundaries.
_Avoid_: walk-forward split, window backtest, fold replay

**Observation Block**:
A fixed, labeled, half-open row range used only to observe **Metrics** on an already-built continuous Portfolio. Blocks never create, truncate, mask, or reset a Portfolio. Internally Aegis represents these ranges with `vbt.Splitter.from_splits` and applies bounds-aware Metric extractors to the unchanged full Portfolio; this internal Splitter is not public Run configuration.
_Avoid_: execution split, held-out window, fold

**ResolvedBook**:
The run-constant terms a **Run's** portfolio simulation trades every **Candidate's** book under: the declared portfolio config together with the per-instrument facts resolved from it — the FX-adjusted trade-fee series, the instrument → drift-band map (the same one the bundle carries), and the continuous-future roots. Resolved once from the Run Config and the Run's currency conversion, so an incoherent config/facts pairing cannot exist as a value (ADR-0026). It is not the book of positions — that is the simulated portfolio.
_Avoid_: book facts, portfolio policy, simulation config

**Candidate Store**:
The durable, cross-**Run** store of published **Candidates** and their **Provenance**. Publishing a **Run's** three representative Candidates into it is what makes them referenceable by later Runs: a **Lock** resolves against the Candidate Store. It is the boundary between results internal to one Run and results visible to all Runs.
_Avoid_: database, candidate cache, results table

**Candidate Key**:
The content-derived identifier that names a **Candidate** across **Runs**, computed from the **Canonical Form** of the Candidate's identity — identical parameters, data, and policy always yield the same key. It is what the **Candidate Store** keys rows by and what a **Lock** role resolves to.
_Avoid_: candidate token, token, candidate hash, candidate_id

**Lock**:
A top-level **Run Config** reference that reproduces one **Candidate** from a prior **Run**. Written as a human-friendly scalar `run_id[:role]`: a bare `run_id` locks the **best** **Candidate** (the default), and `:median`/`:worst` pick the other representatives — the **Run** folder name *is* the `run_id`, so the common case is copy-the-directory-name-and-paste. The precise mapping form `{run_id, candidate_id}` also resolves, where `candidate_id` is a `role` keyword or a raw **Candidate Key**; `run_id` + a resolved **Candidate Key** together *are* the `candidates` primary key, so a Lock needs no separate storage. A `role` resolves to its **Candidate Key** through the storage-free `candidate_rankings` table, and **Lock** provenance always records the resolved hash. A locked Run takes every **Component's** parameters from that Candidate rather than searching for new ones, overriding any `params:` in the config body (the overridden values are recorded in **Evidence**, never silently dropped).
_Avoid_: promotion, lock token, per-component lock, lock_id

**Manifest**:
The immutable audit record of a **Run**. Records lifecycle status, config evidence, environment state, artifact hashes, and stage outcomes.
_Avoid_: log, report, receipt

**Evidence**:
A structured, schema-versioned artifact written by a **Run** stage that records what happened and why. Evidence makes a Run's claims inspectable and reproducible. Examples: config selection record, data quality diagnostics, candidate scoring rows.
_Avoid_: output, result, log

**Canonical Form**:
The deterministic, hash-stable byte representation of a value — sorted keys, strict (no NaN/Inf literals), one encoding rule — that makes a **Manifest** hash, an **Evidence** content hash, and a **Candidate Key** reproducible across processes and machines. **Candidate** identity is a richer, schema-versioned canonicalization layered on top of it.
_Avoid_: serialization, JSON dump, to_builtin

**Metric**:
A registered, named measurement with declared semantics, unit, and ranking eligibility. One Metric is chosen as the primary ranking criterion; all registered Metrics are carried on every **Candidate**.
_Avoid_: score, stat, KPI

**Equity Curve**:
The per-**Candidate** portfolio value series a custom **Metric** reads once from a simulated batch (`get_value`), normalized to a frame with one column per Candidate. It is the single read behind every custom Metric's derivations — drawdown curve, annualized return, daily returns, and benchmark-aligned returns — so a reader honours the one-read-per-batch contract by constructing one Equity Curve and asking it, never re-reading the portfolio.
_Avoid_: NAV, equity, value series, balance

**Exposure Validation**:
The fail-closed check that validates a **Strategy's** signed target-weight frame against the **Run's** **Exposure Limits** — its **Gross Exposure** and **Net Exposure** caps and admissible **Direction** sign — before simulation, and again at live execution inside an Execution Bundle. It neither sizes nor normalizes allocations: the VBT portfolio simulator sizes the signed weights directly and reads **Direction** from their sign. It only rejects books that breach the limits.
_Avoid_: allocation policy, normalizer, sizing engine, portfolio layer

**Exposure Limits**:
The per-**Run** caps a signed target-weight book must satisfy: the **Gross Exposure** cap (`Σ|wᵢ| ≤ gross_cap`), the **Net Exposure** cap (`|Σwᵢ| ≤ net_cap`), and the admissible **Direction** sign. Declared in the run's `portfolio:` config and enforced by **Exposure Validation**.
_Avoid_: allocation policy, risk limits, mandate

**Direction**:
The side an allocation takes, expressed as the sign of a **Strategy's** target weight: a positive weight is long, a negative weight is short. A book with only positive weights is long-only, only negative is short-only, and a mix is long/short.
_Avoid_: side, bias, position type

**Gross Exposure**:
The sum of absolute target weights in a rebalance (Σ|wᵢ|) — total capital at work across both sides. Bounded per **Run** by a gross cap; a gross cap above 1.0 is leverage.
_Avoid_: leverage, notional, total exposure

**Net Exposure**:
The signed sum of target weights in a rebalance (Σwᵢ) — the directional tilt remaining after longs and shorts offset. Bounded per **Run** by a net cap; a net cap at (or near) zero defines a market-neutral book.
_Avoid_: tilt, beta, directional exposure

**Financing Carry**:
The time-based cost of holding a short position: borrowing the security to sell it accrues a borrow fee, partly offset by a rebate earned on the short-sale proceeds. The net carry (borrow minus rebate) is charged per period on the live short notional for as long as the short is held, independent of any gain or loss on the price. A **Run** sets the borrow and rebate as flat annual rates; a long-only book has no short legs and so carries none. Margin interest on borrowed cash is a related but distinct holding cost that this version does not model.
_Avoid_: funding, swap, holding cost, interest

**Provenance**:
The lineage metadata attached to a **Candidate** that traces its parameters back to the **Components** and **Run** that produced them.
_Avoid_: lineage, history, audit trail

**Run Config**:
A declarative YAML specification that fully defines a **Run**: **Data Source Mode**, **Components**, ranking criteria, portfolio settings, and optimization parameters. Configs are inert — they select trusted IDs and parameters only; they cannot execute code or reference generated artifacts.
_Avoid_: spec, recipe, template

**Data Source Mode**:
How market data enters a **Run**: the shared **Historical Store** path, which
may **Ensure Coverage** by filling gaps through a configured **Gap-Fill
Provider** and requires each symbol to declare its canonical **InstrumentId**.
It is the only sourcing — there is no source selection in a **Run Config** —
and it is not the identity under which historical data is stored or traded.
_Avoid_: InstrumentId, store key, execution source, Trader source mode

**RD Symbol Name**:
The column/display name RD uses for one instrument inside a **Run**. For futures
on the `store` path, the RD Symbol Name is the bare continuous-future root
(a `RootSymbol`); it is not authored as a separate label, ticker, or locator.
_Avoid_: InstrumentId, provider locator, store identity, execution identity

**Preflight**:
A fail-closed geometry step before optimization execution. It materializes the exact Candidate sample, resolves the common **Warmup** and scored interval, constructs fixed **Observation Block** bounds, and records expected replay and Metric shapes before any Portfolio is built.
_Avoid_: dry run, split budget, estimate-only validation

**InstrumentId**:
The cross-boundary instrument identity — a Nautilus `InstrumentId` (`{symbol}.{venue}`, e.g. `IDTL.LSEETF`). It is what an **Execution Bundle** carries (`DataContract.instrument_ids`) and what crosses the RD→Trader boundary; the data-provider **ticker** is RD-internal — used only to fetch market data — and never crosses into an Execution Bundle. `aerd export` bakes each declared instrument's `InstrumentId` into the bundle's data contract, and live resolution hands those ids to IBKR's `InstrumentProvider` (root ADR-0007). There is no FIGI hub, no `InstrumentRef` variant, and no bespoke Security Master — FIGI is retired as an identity term. Currency and venue detail are carried by the `{symbol}.{venue}` id and resolved IBKR-native, not carried alongside it.
_Avoid_: FIGI, InstrumentRef, ListedRef, FuturesRef, Security Master, ISIN, CUSIP, ticker, symbol

## Example dialogue

> **Dev**: I want to test a moving-average crossover idea on ETFs.
>
> **Expert**: Write an **Indicator** for the moving average and a **Strategy** that consumes it. Define a parameter space in each, then create a **Run Config** that chooses Observation Block length and ranks Candidates by mean within-block Sharpe rank over one continuous Development replay.
>
> **Dev**: What if the best **Candidate** looks good?
>
> **Expert**: The **Run** produces three representative **Candidates** — best, median, and worst — with complete-period Metrics, per-Observation-Block Metrics, and a mean rank. Review the evidence across regimes, then **Lock** a representative and reference that Lock in a new Run Config to reuse its exact parameters.
>
> **Dev**: How do I know the **Run** was honest?
>
> **Expert**: Every **Run** writes a **Manifest** with **Evidence** — config hashes, data quality diagnostics, component source hashes. The **Manifest** is immutable once the **Run** completes.
