---
date: 2026-05-22
topic: portfolio-target-allocation-pfo-contract
---

# Portfolio: Target Allocation as the Forward Multi-Asset Contract (PFO Substrate)

Source: issue #35. Supersedes the v1 portfolio substrate established in `docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md` for multi-asset research.

## Problem Frame

Aegis's current multi-asset portfolio runtime is event-style: components emit `entries`/`exits` and the runner calls `vbt.Portfolio.from_signals(..., size_type="valuepercent")`. This boundary is trade-event-oriented — it works for independent trade lifecycle studies but is the wrong public truth for shared-cash, multi-symbol research. It cannot naturally express "sell down current holdings and allocate to the new active set," and continuous target exposure, equal-weight active books, ranked top-N rebalancing, and path-dependent allocation are awkward to encode as entries/exits.

The original portfolio simulation contract (issue #4, 2026-05-18) explicitly named `vbt.PortfolioOptimizer` (PFO) as the correct substrate for target/allocation work and deferred it because v1 components emitted entry/exit signals, not weights. This brainstorm activates that deferred path: the multi-asset public truth becomes "at this timestamp, what should the portfolio weights be?" and PFO becomes the single forward substrate. There is no transitional `entries`/`exits` adapter inside the multi-asset runtime — components are converted in the migration, not bridged.

This also aligns the portfolio substrate with the VBT-native optimization performance plan (`docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md`), whose batched candidate path is designed to feed a wide allocations frame through PFO in one simulation call per split.

---

## Actors

- A1. **Strategy / alpha components**: emit one declared allocation-native output shape per component (scores | ranks | active | target_weights). Do not own portfolios, official metrics, or arbitrary VBT kwargs.
- A2. **Portfolio policy**: Aegis-owned conversion layer that turns component output into a validated allocations frame and applies split-aware executable masking before PFO sees it. Enforces longonly, target exposure cap, no duplicate symbols, no unauthorized leverage, no short exposure.
- A3. **Portfolio runner**: single forward path. Wraps the validated allocations frame via `vbt.PFO.from_filled_allocations(...)` and calls `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", ...)`.
- A4. **Optimization runner (multi-candidate)**: same forward path, but with `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` + `cash_sharing=True` so each candidate is its own shared-cash group. Consumes the wide allocations frame produced by the batched parameterized callable.
- A5. **Config validator**: rejects arbitrary `portfolio.size`, arbitrary `portfolio.size_type`, raw VBT kwargs, component-owned portfolios, source-owned metrics, and the legacy `portfolio.entry_budget` name.
- A6. **Diagnostics / reporting**: consumes the post-simulation `pf` plus PFO artefacts (`allocations`, `filled_allocations`, `alloc_records`) for evidence rows.

---

## Key Flows

- F1. **Single-portfolio simulation**
  - **Trigger:** Runner invokes the multi-asset portfolio simulation with a single candidate.
  - **Actors:** A1, A2, A3, A6.
  - **Steps:** Component emits its declared allocation-native output. Portfolio policy converts and validates into an allocations frame (date × symbol; `NaN` = no rebalance; `0.0` = real target). Split-aware executable masking is applied before PFO. Runner calls `vbt.PFO.from_filled_allocations(allocations)` then `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", size_type="targetpercent", direction="longonly", cash_sharing=True, call_seq="auto", group_by=True, price="nextopen", ...)`. Diagnostics record target source, target exposure cap, grouping, factory, size type, rebalance rows from `pfo.alloc_records`, and realized-vs-requested allocation at fill rows.
  - **Outcome:** One `pf` with PFO-native allocation diagnostics. Decision time and fill time are recorded separately.
  - **Covered by:** R1, R2, R3, R4, R5, R6, R7, R8, R10, R11, R13, R14.

- F2. **Multi-candidate batched simulation**
  - **Trigger:** Optimization runner invokes the batched candidate portfolio path (one simulation call per split).
  - **Actors:** A1, A2, A4, A6.
  - **Steps:** Inner `@vbt.parameterized(merge_func="column_stack", mono_chunk_len=…)` callable produces a wide allocations frame (date × (candidate × symbol), `NaN` = no rebalance). The wide frame is wrapped via `vbt.PFO.from_filled_allocations(...)` and simulated via `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", group_by=vbt.ExceptLevel(SYMBOL_LEVEL), cash_sharing=True, ...)`. PFO's `group_configs` carry candidate identity through the multi-level column structure.
  - **Outcome:** One simulated `pf` covering all candidates in the split, with each candidate as its own shared-cash group.
  - **Covered by:** R1, R3, R5, R9, R10, R11, R13, R14.

- F3. **Component registration**
  - **Trigger:** A component is registered for multi-asset optimization.
  - **Actors:** A1, A5.
  - **Steps:** Component declares exactly one of {scores, ranks, active, target_weights} in its registration contract. The validator rejects any registration that does not declare an allocation-native output shape, including any attempt to register `entries`/`exits`.
  - **Outcome:** Only allocation-native components reach the portfolio policy.
  - **Covered by:** R2, R12.

---

## Requirements

**Substrate and forward path**
- R1. The only public forward path for multi-asset portfolio simulation is `vbt.PFO.from_filled_allocations(allocations)` followed by `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", ...)`. No direct `Portfolio.from_orders` or `Portfolio.from_signals` calls exist in the multi-asset runtime. `pf_method="from_signals"` is rejected for v1 (dynamic-signal compilation cost).
- R2. Components emit exactly one declared allocation-native output: `scores` (date × symbol alpha scores), `ranks` (date × symbol rank/order), `active` (date × symbol bool mask), or `target_weights` (date × symbol final desired weights). `entries`/`exits` is not a registrable output shape and is not bridged at runtime.
- R3. Aegis portfolio policy owns conversion of any of {scores, ranks, active} into a validated allocations frame consumable by `vbt.PFO.from_filled_allocations(...)`. `target_weights` components produce the allocations frame directly (still subject to validation). Components do not call PFO and do not own portfolios, official metrics, or arbitrary VBT kwargs.
- R4. The allocations frame uses `NaN` for "no rebalance" rows and `0.0` as a real target (closes existing position). `fill_value` stays `np.nan`; filling with `0.0` is rejected because it converts "no rebalance" into "exit".

**Execution semantics**
- R5. v1 execution policy is close-decision, next-open execution: target computed at `t close`, executed at `t+1 open` via `price="nextopen"`. `target_weights[t] = 0` under `price="nextopen"` means flat after the next executable open and still holds overnight from `t close` to `t+1 open`. `open_to_close` is out of v1 scope.
- R6. Direction is forced to `"longonly"` at the runner boundary. The runtime does not rely on `from_optimizer`'s auto-inference of direction from allocation values.
- R7. `call_seq="auto"` is frozen for v1. No custom path-dependent engine.
- R8. Split-aware executable masking is applied to the allocations frame inside Aegis policy **before** the frame reaches PFO, so PFO never sees rows it shouldn't execute. Terminal/gap non-executable rows under `price="nextopen"` are counted by the existing diagnostics before the frame reaches PFO.

**Grouping and candidate batching**
- R9. Single-portfolio runs use `group_by=True` (one shared-cash group across all symbols). Multi-candidate optimization runs use `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` so each candidate is its own shared-cash group across its symbols. `cash_sharing=True` in both cases.
- R10. The batched candidate path composes with PFO's `group_configs` for multi-candidate column structures and preserves candidate identity through PFO's multi-level columns. The substrate switch from `from_signals` to PFO-backed `from_orders` does not change the `column_stack` + `mono_chunk_len` parameterization or candidate identity handling at the optimization layer.

**Naming and config validation**
- R11. `portfolio.entry_budget` is renamed to `portfolio.target_exposure_cap` (gross exposure cap, units of portfolio value). There is no dual-name period; the old name is removed in the migration PR and rejected by config validation.
- R12. Config validation rejects: arbitrary `portfolio.size`, arbitrary `portfolio.size_type`, raw VBT kwargs that bypass Aegis policy, component-owned portfolios, source-owned metrics, the legacy `portfolio.entry_budget` name, and component registrations whose declared output is not one of {scores, ranks, active, target_weights}.

**Diagnostics**
- R13. Diagnostics record: target source, target exposure cap, rebalance rows (from `pfo.alloc_records`), grouping, VBT factory (`Portfolio.from_optimizer`), `pf_method="from_orders"`, size type (`targetpercent`), requested target weights (`pfo.filled_allocations`), and realized allocation at rebalance fill rows compared against the requested allocation. The legacy fields `allocation_mode: "event_style_signals"` and `rebalances_existing_positions: False` are removed; they do not appear in any v1 diagnostics output.
- R14. Execution docs and diagnostics define decision time and fill time as separate fields. `next_open` target zero is documented as "flat after next executable open," not "flat by same close."

**Migration completeness (no side paths)**
- R15. Every in-tree component is converted to an allocation-native output in the same migration PR that replaces the substrate. There is no opt-in legacy mode, no runtime `allocation_mode` choice, and no `entries`/`exits` adapter into target weights.
- R16. The current portfolio runtime code is replaced, not preserved alongside the new code: `simulate_portfolio` and `simulate_portfolio_batch` in `research/aegis_research/portfolios.py` are rewritten to consume an allocations frame and call `vbt.Portfolio.from_optimizer`; `VBT_PORTFOLIO_FACTORY = "Portfolio.from_signals"` and `VBT_RESOLVED_SIZE_TYPE = "valuepercent"` are replaced; `_entry_size_frame` and `_candidate_entry_size_frame` are removed (their replacement is target-weight validation in portfolio policy).
- R17. Tests that lock in entries/exits multi-asset semantics are removed in the migration PR — specifically `test_later_entries_do_not_rebalance_existing_positions` and any other test asserting the same shape. Public docs are rewritten so target allocation (PFO substrate) is described as the only multi-asset contract.

---

## Acceptance Examples

- AE1. **Covers R4, R5.** Given an allocations frame with `target_weights[t]` = `{A: 0.5, B: 0.5}` and `target_weights[t+1]` = `NaN`, when simulated with `price="nextopen"`, then the rebalance executes at `t+1` open and no rebalance occurs at `t+2` open; positions persist through the `NaN` row.
- AE2. **Covers R4, R5.** Given the portfolio is fully allocated to A and `target_weights[t]` = `{A: 0.0, B: 0.0}`, when simulated with `price="nextopen"`, then both A and B are flat after the next executable open. The `0.0` row is treated as a real target, not a no-rebalance row.
- AE3. **Covers R1, R3.** Given a component declares output shape `active` and emits `{A: True, B: True, C: False}` at `t`, when portfolio policy converts it under longonly + `target_exposure_cap=1.0`, then the resulting allocations row is `{A: 0.5, B: 0.5, C: 0.0}` and is fed into `vbt.PFO.from_filled_allocations(...)` for simulation via `vbt.Portfolio.from_optimizer(..., pf_method="from_orders")`.
- AE4. **Covers R3, R4, R5.** Given the portfolio is fully allocated to A at `t-1` and `target_weights[t]` = `{B: 1.0}` (A omitted as NaN at this row would mean no-rebalance, so instead the policy emits `{A: 0.0, B: 1.0}`), when simulated with `price="nextopen"`, then A is sold down and B is bought at `t+1` open under shared cash.
- AE5. **Covers R9, R10.** Given two candidates over symbols {A, B, C} with separate allocations frames stacked column-wise (via `column_stack` + `mono_chunk_len`), when simulated with `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` + `cash_sharing=True`, then each candidate is its own shared-cash group, candidate identity is preserved in `pfo.allocations`/`pfo.alloc_records`, and one `Portfolio.from_optimizer` call covers the entire split.
- AE6. **Covers R8.** Given a terminal-gap non-executable row under `price="nextopen"`, when the allocations frame is built, then the existing next-open diagnostics count the row as non-executable before the frame reaches PFO, and PFO does not receive a row it cannot execute.
- AE7. **Covers R12.** Given a component manifest declares output shape `entries`, when registration is attempted, then registration fails with a contract violation pointing at the unsupported output shape.
- AE8. **Covers R13.** Given a completed multi-asset run, when diagnostics are written, then they contain `target_exposure_cap`, `pfo.filled_allocations`, rebalance rows from `pfo.alloc_records`, factory = `Portfolio.from_optimizer`, `pf_method = "from_orders"`, `size_type = "targetpercent"`, and a realized-vs-requested allocation comparison at fill rows; they do not contain `allocation_mode: "event_style_signals"` or `rebalances_existing_positions: False`.

---

## Success Criteria

- A maintainer reading `research/aegis_research/portfolios.py` after the migration sees `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", ...)` as the only multi-asset simulation call; no `Portfolio.from_signals` or direct `Portfolio.from_orders` call survives in that path.
- A new component author following the public docs writes a component that declares one of {scores, ranks, active, target_weights}, does not call PFO or VBT, and runs correctly through the portfolio policy without any bridge code.
- A reader of the public docs learns target allocation as the only multi-asset portfolio contract. `entries`/`exits` is not presented as an option for multi-asset construction anywhere.
- Diagnostics produced by a v1 run contain the PFO-native fields enumerated in R13 and do not contain the removed legacy fields, with no manual fix-up required downstream.
- The VBT-native optimization performance plan's batched candidate path (Phase B / U2) builds on this substrate from the start without needing a substrate-swap step of its own.
- `/ce-plan` can produce an implementation plan from this document without inventing product behavior, scope boundaries, or success criteria. The remaining open items are implementation decisions, not product decisions.

---

## Scope Boundaries

- No `pf_method="from_signals"` in v1 — the dynamic-signal compilation cost is unacceptable and stop/limit support inside the optimizer is not a v1 requirement.
- No `vbt.PFO.from_pypfopt`, `from_riskfolio`, `from_universal_algo`, `from_optimize_func`, or `from_allocate_func` constructors in v1. Periodic-cadence rebalancing via `from_optimize_func(..., every=…)` is a known follow-up.
- No `open_to_close` execution policy in v1. Sub-bar ordered open/close rows are a future milestone.
- No `portfolio.min_rebalance_size` / inertia (continuous or scheduled) and no drift-threshold rebalancing in v1.
- No runtime `allocation_mode` choice, no `entries`/`exits` adapter, no opt-in legacy path, no dual-name period for `entry_budget` → `target_exposure_cap`. Forward-first single path or fail closed.
- Components do not own portfolios, official metrics, or arbitrary VBT kwargs in any phase.
- Nautilus runtime adapter (translating target weights into order diffs) is out of scope. Aegis does not port ambiguous `entries`/`exits` portfolio semantics into a future runtime.

---

## Key Decisions

- **PFO is the substrate, not direct `Portfolio.from_orders`**: PFO is the documented practitioner-preferred primitive for "given allocations, scores, ranks, or rules → simulate a multi-asset portfolio." It provides allocations storage, `filled_allocations` validation, `alloc_records`, `mean_allocation`, `group_configs` for multi-candidate, and the `Portfolio.from_optimizer` handoff (which internally calls cached `Portfolio.from_orders`). Direct `from_orders` would force Aegis to rebuild all of these.
- **`pf_method="from_orders"` is locked for v1**: it is the cacheable/fast simulation path. `from_signals` triggers PFO's dynamic-signal compilation (~1-minute first call) and is rejected.
- **`from_filled_allocations` over `from_optimize_func`**: Aegis's research workflow is event-driven — allocations may change every bar. Scheduled cadence becomes useful later as a separate constructor.
- **`size_type="targetpercent"` and `direction="longonly"` restated explicitly**: do not rely on PFO defaults or `from_optimizer`'s direction inference from allocation values.
- **`call_seq="auto"` frozen for v1**: keeps order-of-execution behavior consistent with VBT's default and avoids a custom path-dependent engine.
- **Component output is exactly one declared shape**: not a union, not a fallback chain. Declared at registration and enforced there.
- **No transitional `entries`/`exits` adapter**: every in-tree component is converted in the migration PR. Bridging would mean a permanent second public output shape, which Forward-First rejects.
- **Acceptable scope of this issue**: substrate switch + component conversion + naming + diagnostics + docs + test removal, all in the migration PR. Lands before or concurrently with the VBT optimization plan's Phase B/U2.

---

## Dependencies / Assumptions

- VBT API surface relied on: `vbt.PFO.from_filled_allocations`, `vbt.Portfolio.from_optimizer(..., pf_method="from_orders")`, `pfo.alloc_records`, `pfo.allocations`, `pfo.filled_allocations`, `group_configs`. The issue body documents the relevant edge cases (`fill_value=np.nan`, `nonzero_only=False` default, `price="nextopen"` row-shift behavior, longonly inference quirks). Verification against the installed VBT PRO version belongs in planning.
- The VBT-native optimization performance plan (`docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md`) is the consumer of the batched-candidate forward shape (F2) and is expected to land before or concurrently. Sequencing is a planning decision.
- The component candidate promotion workflow (`docs/brainstorms/2026-05-21-component-candidate-promotion-requirements.md`) and the component manifests touched by the migration follow the same allocation-native registration rule — there is no carve-out for legacy components.
- Verified file/symbol references at brainstorm time: `research/aegis_research/portfolios.py` contains `VBT_PORTFOLIO_FACTORY = "Portfolio.from_signals"`, `VBT_RESOLVED_SIZE_TYPE = "valuepercent"`, `simulate_portfolio`, `simulate_portfolio_batch`, `_entry_size_frame`, `_candidate_entry_size_frame`, the `allocation_mode` / `event_style_signals` / `rebalances_existing_positions` diagnostic fields, and the `entry_budget` config field. `test_later_entries_do_not_rebalance_existing_positions` lives in `tests/integration/research/aegis_research/test_portfolios.py`. Any other test or component manifest discovery is a planning concern.

---

## Outstanding Questions

### Resolve Before Planning

- *(none)*

### Deferred to Planning

- [Affects R3][Technical] Where exactly in the portfolio policy module does conversion of {scores, ranks, active} → allocations live (single function vs strategy-per-shape), and what is its tested surface? The contract is fixed; the internal shape is a planning decision.
- [Affects R8][Technical] Precise placement and reuse of the existing split-aware executable masking layer relative to the new policy module — keep in current location, move into policy, or extract into a shared utility.
- [Affects R10][Technical] How candidate identity is encoded in the wide allocations frame (column hierarchy levels and labels) so it survives `column_stack` + `mono_chunk_len` and lines up cleanly with `pfo.group_configs`. Planning should verify against the existing optimization plan.
- [Affects R13][Technical] Diagnostic payload schema (field names, nesting, JSON shape) for the new PFO-native fields, plus how the realized-vs-requested allocation comparison is structured (per-symbol, per-rebalance row, per-candidate). Names of removed legacy fields are decided; new field shape is open.
- [Affects R15, R17][Technical] Full inventory of components whose registered output shape changes, plus the inventory of removed/rewritten tests beyond `test_later_entries_do_not_rebalance_existing_positions`. Discovery work belongs in planning.
- [Affects R11][Needs research] Whether any out-of-tree consumers or examples reference `portfolio.entry_budget` by name. The decision (no dual-name period) is fixed regardless; planning should still surface affected call sites.

---

## Next Steps

-> `/ce-plan` for structured implementation planning.
