---
date: 2026-05-18
topic: portfolio-simulation-contract
github_issue: 4
---

# Portfolio Simulation Contract

## Summary

Issue #4 will harden the portfolio layer as an auditable shared-cash signal simulation contract. V1 keeps `Portfolio.from_signals` for event-style long-only entries and exits, uses value-percent sizing against portfolio value, requires an explicit shared-cash entry budget, and reserves target-weight rebalancing for `from_orders`, PortfolioOptimizer, or future custom execution contracts.

---

## Problem Frame

`research/aegis_research/portfolios.py` is where model-derived signals become simulated PnL. Issue #11 already resolved the most dangerous signal ambiguities: v1 is long-only, defaults to next-open execution, delegates repeated-signal behavior to VectorBT, disables accumulation, records conflict/timing diagnostics, and rejects accidental short or reversal behavior.

The remaining risk is multi-symbol shared-cash behavior. Shared cash means all symbols draw from one portfolio cash pool instead of each symbol behaving like an independent mini-backtest. That is the right direction for realistic multi-asset runs, but it introduces allocation and ordering assumptions: simultaneous entries compete for cash, exits may free cash for buys, and a raw signal does not by itself define target portfolio weights.

VectorBT PRO guidance separates these concepts. Boolean entry/exit signals are suitable for event-style `from_signals` simulations, where `valuepercent` sizes each entry as a share of portfolio value. Continuous target exposure, equal-weight active books, ranked top-N rebalancing, and path-dependent allocation are allocation problems and should use `from_orders`, PortfolioOptimizer, or `from_order_func` instead of hiding rebalancing semantics inside a signal wrapper.

---

## Actors

- A1. Experiment author: Chooses shared-cash portfolio assumptions, entry budget, sizing mode, timing mode, fees, slippage, and portfolio factory for a run.
- A2. Portfolio stage: Converts validated signal panels and portfolio assumptions into a VectorBT portfolio simulation.
- A3. Run reviewer or automation agent: Inspects public artifacts to understand whether reported PnL came from signals, sizing, shared-cash ordering, or a target-weight allocation mode.
- A4. Future allocation-strategy developer: Adds target-weight, ranked, or dynamic allocation behavior without inheriting ambiguous `from_signals` semantics.

---

## Key Flows

- F1. Run shared-cash signal simulation
  - **Trigger:** A long-only signal run has timestamp-by-symbol close/open data and raw entry/exit state panels.
  - **Actors:** A1, A2, A3
  - **Steps:** Validate aligned price and signal panels, require an explicit total entry budget for shared-cash multi-symbol runs, size active entries as value-percent shares of portfolio value, process exits before buys, and record the resolved simulation assumptions.
  - **Outcome:** The portfolio result represents event-style shared-cash signal entries, not an implicit target-weight rebalance.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R9, R10
- F2. Reject or defer target-weight allocation behavior
  - **Trigger:** A strategy expectation asks for equal-weight active positions, ranked top-N selection, continuous rebalancing, or shrinking existing positions when new entries appear.
  - **Actors:** A1, A2, A4
  - **Steps:** Classify the request as an allocation contract rather than a signal-entry contract, direct it to a target-weight or dynamic execution mode, and avoid silently approximating it through `from_signals` entry sizing.
  - **Outcome:** Allocation strategies use the correct VectorBT abstraction instead of producing misleading signal-simulation PnL.
  - **Covered by:** R7, R8, R11, R12, R13
- F3. Review portfolio evidence
  - **Trigger:** A run writes portfolio diagnostics, metrics, and native artifacts.
  - **Actors:** A1, A3
  - **Steps:** Inspect public metadata for portfolio factory, shared-cash grouping, sizing mode, entry budget, timing, order sequence, order/trade counts, and known limitations.
  - **Outcome:** Reviewers can audit simulation assumptions without loading private VectorBT objects or rereading implementation code.
  - **Covered by:** R9, R10, R14, R15, R16

---

## Evidence Used

- VectorBT PRO API for `Portfolio.from_signals` confirms it supports broadcastable `size`, `size_type`, `price`, `cash_sharing`, `group_by`, `call_seq`, `open`/`high`/`low`, stops, records, logs, and benchmark inputs; negative size is not the way to express direction.
- VectorBT PRO API for `cash_sharing` warns that shared-cash groups create cross-asset dependencies and assume grouped orders execute in the same tick while retaining their price.
- VectorBT PRO API for `call_seq="auto"` confirms it can sort sell orders before buy orders, while warning that automatic sequencing assumes predetermined order prices and flexible execution.
- VectorBT PRO support guidance says `percent` sizes against available cash, while `valuepercent` sizes against portfolio value and is the better fit for signal-sized shared-cash entries.
- VectorBT PRO support guidance says target allocations, equal-weight active books, and rebalancing are better represented through `from_orders`, PortfolioOptimizer, or dynamic signal/order functions rather than ordinary `from_signals` entries.
- Existing repo contract docs already establish native market-data inputs, long-only probability-to-signal semantics, next-open timing, and raw signal diagnostics in `docs/vectorbt-scaffold.md` and `docs/brainstorms/2026-05-17-signal-generation-conflict-semantics-requirements.md`.

---

## Requirements

**Shared-cash signal simulation**
- R1. V1 portfolio simulation must support shared-cash multi-symbol runs as one portfolio cash pool across the configured symbol group, not independent per-symbol cash pools.
- R2. Shared-cash v1 must remain event-style: entry signals open or add exposure according to their configured entry size, and exit signals close exposure according to VectorBT signal semantics.
- R3. Shared-cash v1 must not automatically rebalance existing positions when new entry signals appear.
- R4. Multi-symbol shared-cash runs must require an explicit total entry budget that states the maximum portfolio-value share available to same-bar entries.
- R5. Same-bar entry sizing must allocate the explicit entry budget across active entry signals using value-percent sizing against portfolio value, not available-cash percent sizing.
- R6. A single entry signal may receive the whole explicit entry budget only because the run made that budget explicit, not because the system silently defaulted to 100% allocation.

**Ordering and VectorBT assumptions**
- R7. Shared-cash v1 must process exits/sells before entries/buys when both occur in the same bar so exits can free cash for entries.
- R8. The sell-before-buy order sequence must be recorded as a simulation assumption, including VectorBT's predetermined-price/flexible-execution caveat.
- R9. The portfolio diagnostics or metadata must record the VectorBT portfolio factory, sizing mode, direction, accumulation mode, shared-cash setting, grouping behavior, order sequence, timing mode, fees, slippage, and entry-budget interpretation.
- R10. Portfolio diagnostics must preserve the existing distinction between raw threshold-state counts and actual VectorBT order/trade counts.

**Boundary to allocation modes**
- R11. Equal-weight active-book behavior, ranked top-N selection, target-weight matrices, and continuous rebalancing must be treated as allocation contracts, not hidden behaviors inside shared-cash signal simulation.
- R12. When a strategy requires target exposure after each rebalance, the requirements must direct it to `from_orders`, PortfolioOptimizer, or a future allocation contract rather than `from_signals` entry sizing.
- R13. When a strategy requires path-dependent allocation, position caps, deferred entries when cash becomes available, or custom cash-aware execution, the requirements must direct it to dynamic signal/order functions or `from_order_func` rather than the baseline v1 wrapper.

**Auditability and metrics**
- R14. Public artifacts must make shared-cash assumptions inspectable without loading private native VectorBT portfolio artifacts.
- R15. Portfolio metrics must identify the frequency and benchmark assumptions used for time-based and relative metrics, whether those assumptions are passed directly into portfolio construction or resolved in reporting.
- R16. Native portfolio artifacts may remain private/local, but public sidecar metadata must contain enough information to reproduce or challenge the simulation assumptions.

---

## Acceptance Examples

- AE1. **Covers R1, R4, R5, R6.** Given a shared-cash run with three symbols and two entry signals on the same bar, when the run declares a 60% total entry budget, each active entry is sized as 30% of portfolio value for that bar.
- AE2. **Covers R4, R6.** Given a multi-symbol shared-cash run omits an entry budget, when portfolio simulation is prepared, the run fails before producing portfolio artifacts instead of silently allocating 100% of portfolio value.
- AE3. **Covers R3, R11, R12.** Given one symbol is already open at 60% and a second symbol receives a new entry, when the strategy expectation is to rebalance both to 50%, the run is classified as a target-weight allocation problem rather than modeled by baseline signal sizing.
- AE4. **Covers R7, R8.** Given one symbol exits and another symbol enters on the same bar in shared-cash mode, when simulation runs, sell-before-buy ordering is used and the diagnostics record the order-sequence caveat.
- AE5. **Covers R9, R10, R14, R16.** Given a completed shared-cash portfolio run, when a reviewer opens public artifacts, they can see the portfolio factory, shared-cash setting, entry budget, sizing mode, timing mode, order sequence, raw signal counts, and actual order/trade counts.
- AE6. **Covers R11, R12, R13.** Given a strategy asks for ranked top-N active positions with continuous equal-weight rebalancing, when reviewed against the v1 contract, it is deferred to an allocation mode using `from_orders`, PortfolioOptimizer, or custom dynamic execution.
- AE7. **Covers R15.** Given a run reports Sharpe or benchmark-relative performance, when metrics are written, the frequency and benchmark assumptions are visible in public metadata or report artifacts.

---

## Success Criteria

- Shared-cash multi-symbol backtests no longer rely on hidden per-entry 100% allocation, arbitrary column-order fills, or available-cash percent sizing.
- Experiment authors can distinguish event-style signal simulation from target-weight allocation before trusting results.
- Reviewers can understand portfolio factory choice, shared-cash grouping, entry budget, order sequencing, timing, sizing, and metric assumptions from public artifacts.
- Downstream planning can implement issue #4 without inventing the shared-cash allocation rule, the `from_signals`/`from_orders` boundary, or the scope exclusions.

---

## Scope Boundaries

- No equal-weight active-book rebalancing in baseline shared-cash v1.
- No ranked top-N allocation, probability-ranked allocation, optimizer-driven allocation, or target-weight matrix support in baseline shared-cash v1.
- No automatic shrinking of existing positions when new entries appear.
- No custom `from_order_func` simulator, intrabar event engine, deferred-entry retry loop, or dynamic cash-aware allocation callback in this issue.
- No short-only, long/short, reversal, leverage, margin, borrowing, futures multiplier, or side-specific allocation behavior beyond the long-only v1 signal contract.
- No advanced stop-loss or take-profit expansion in this issue; stop behavior remains governed by the existing signal/portfolio contract and VectorBT limitations.
- No backward-compatibility shim for older portfolio semantics unless planning discovers a persisted artifact or external consumer that requires migration handling.

---

## Key Decisions

- Shared cash is in scope for v1: Multi-symbol portfolio results should represent one cash pool because that matches the intended research shape better than independent per-symbol cash.
- `from_signals` remains the baseline factory: The current product emits event-style entry/exit signals, not target weights.
- `valuepercent` is the signal-sizing mode: It sizes against portfolio value and avoids the progressive available-cash decay of percent sizing.
- Entry budget is explicit: Hidden 100% allocation would make one-signal and many-signal bars too easy to misread.
- Sell-before-buy is the v1 ordering stance: It is the practical shared-cash default, but its predetermined-price caveat must be visible.
- Allocation modes are separate contracts: Equal-weight, ranked, and target-weight behavior should use `from_orders`, PortfolioOptimizer, or future dynamic execution paths.

---

## Dependencies / Assumptions

- Issue #11 defines the long-only signal contract, next-open default, raw threshold-state diagnostics, conflict visibility, and no-short v1 boundary.
- `docs/brainstorms/2026-05-16-vectorbt-market-data-contract-requirements.md` defines the native market-data and OHLCV feature availability expectations this portfolio contract consumes.
- `docs/brainstorms/2026-05-17-signal-generation-conflict-semantics-requirements.md` defines raw signal state semantics and timing assumptions this portfolio contract extends.
- Current portfolio simulation lives in `research/aegis_research/portfolios.py`, current portfolio config lives in `research/aegis_research/config.py`, and current portfolio tests live in `tests/research/aegis_research/test_portfolios.py`.
- VectorBT PRO behavior cited here is current as of 2026-05-18 based on MCP-backed docs and support context.
- The project principles in `AGENTS.md` favor forward-first contracts, fail-fast validation, visible errors, and no silent fallbacks.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4, R5][Technical] What exact config shape should express the shared-cash entry budget without overloading the existing scalar `size` meaning?
- [Affects R5][Technical] Should entry-budget splitting count only current-bar entry signals, or should planning add an optional later mode that accounts for already-open positions while still avoiding full rebalancing?
- [Affects R7, R8][Technical] What exact VectorBT `group_by`, `cash_sharing`, and `call_seq` values should be passed for the baseline, and how should the resolved values be serialized in diagnostics?
- [Affects R9, R14, R16][Technical] What artifact schema should store portfolio factory parameters, shared-cash assumptions, entry budget, and metric assumptions without duplicating large native portfolio objects?
- [Affects R15][Technical] Should portfolio frequency and benchmark assumptions be passed into portfolio construction, reporting, or both, given the current report-level metric calculation?
