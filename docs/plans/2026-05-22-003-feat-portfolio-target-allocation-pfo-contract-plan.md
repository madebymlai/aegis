---
title: "Portfolio: Target Allocation as the Forward Multi-Asset Contract (PFO Substrate)"
type: feat
status: active
date: 2026-05-22
deepened: 2026-05-22
origin: docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md
---

# Portfolio: Target Allocation as the Forward Multi-Asset Contract (PFO Substrate)

## Overview

Replace the Aegis multi-asset portfolio runtime substrate from `vbt.Portfolio.from_signals(..., size_type="valuepercent")` driven by component `entries`/`exits` outputs to a target-allocation contract built on `vbt.PFO.from_filled_allocations(...)` + `vbt.Portfolio.from_optimizer(..., pf_method="from_orders")`. Components declare exactly one allocation-native output shape ({scores, ranks, active, target_weights}); an Aegis portfolio policy converts and validates into an allocations frame; the runtime hands that frame to PFO and returns one `vbt.Portfolio`. Forward-first, no adapters, no opt-in legacy mode, no dual-name period for `entry_budget → target_exposure_cap`. Every in-tree component is converted in the same PR.

This plan supersedes the dependency hedge in `docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md` (U2/U5) by becoming its prerequisite — the optimization performance plan's batched candidate path builds on this substrate from the start.

---

## Problem Frame

Aegis's current multi-asset portfolio runtime is event-style: components emit `entries`/`exits` and the runner calls `vbt.Portfolio.from_signals(..., size_type="valuepercent")`. This boundary works for independent trade lifecycle studies but is the wrong public truth for shared-cash, multi-symbol research — it cannot naturally express "sell down current holdings and allocate to the new active set," and continuous target exposure, equal-weight active books, and ranked top-N rebalancing are awkward to encode as entries/exits. The original portfolio simulation contract (issue #4, 2026-05-18) explicitly named PFO as the correct substrate for target/allocation work and deferred it because v1 components emitted entry/exit signals. This plan activates that deferred path (see origin: `docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md`).

---

## Requirements Trace

- R1. Only public forward path for multi-asset is `vbt.PFO.from_filled_allocations(allocations)` + `vbt.Portfolio.from_optimizer(close, pfo, pf_method="from_orders", ...)`. No direct `Portfolio.from_orders` / `Portfolio.from_signals` in the multi-asset runtime; `pf_method="from_signals"` rejected.
- R2. Components emit one declared allocation-native output: {scores, ranks, active, target_weights}. All four are registrable in v1. `entries`/`exits` is not in the category and is not bridged.
- R3. Aegis portfolio policy owns conversion of declared shapes into a validated allocations frame.
- R4. Allocations frame uses NaN = "no rebalance" and 0.0 = real target (closes position). `fill_value=np.nan` retained.
- R5. v1 execution: close-decision, **close execution** via default `price="close"`. Target computed at `t` close, executed at `t` close — same-bar. Single forward path; no opt-in `nextopen`/`open` alternative. Matches the dominant VBT cross-sectional target-allocation pattern (verified across the official VBT cookbook, `from-orders/#call-sequence_1`, the `top10_nasdaq100_v2` notebook, and the maintainer's blessed terminal-handling pattern). `target_weights[t] = 0` closes existing positions at `t` close. Maintainer's stance on lookahead: "Using today's close doesn't introduce lookahead bias; it just lets you trade signals immediately, as in live trading where reaction times can be milliseconds."
- R6. `direction="longonly"` forced; no reliance on auto-inference.
- R7. `call_seq="auto"` frozen for v1.
- R8. Split-aware executable masking applied to the allocations frame **before** PFO sees it; non-executable rows due to split-gaps are counted in diagnostics. **Terminal liquidation: the policy module forces `allocations.iloc[-1] = 0.0` for any symbol that would otherwise hold a position into the terminal bar. This implements the maintainer's blessed terminal-handling pattern under default `price="close"` and is empirically verified to produce a cash-realized terminal (no MTM phantom).**
- R9. `group_by=True` for single, `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` for multi-candidate, `cash_sharing=True` in both.
- R10. Batched candidate path composes with PFO `group_configs`; preserves candidate identity through PFO multi-level columns. `column_stack` + `mono_chunk_len` parameterization unchanged.
- R11. `portfolio.entry_budget` renamed to `portfolio.target_exposure_cap`; old name removed and rejected by config validation, no dual-name period.
- R12. Config validation rejects arbitrary `portfolio.size`, arbitrary `portfolio.size_type`, raw VBT kwargs, component-owned portfolios, source-owned metrics, legacy `entry_budget` name, and component registrations whose declared output is not one of the four allocation-native shapes.
- R13. Diagnostics record target source, target_exposure_cap, rebalance rows (from `pfo.alloc_records`), grouping, factory (`Portfolio.from_optimizer`), `pf_method="from_orders"`, `size_type="targetpercent"`, requested target weights (`pfo.filled_allocations`), realized-vs-requested allocation at fill rows. Legacy fields removed.
- R14. Execution semantics documented in public docs: same-bar close decision and close execution. Terminal liquidation: any position held into the terminal bar is closed at the terminal bar's close via `allocations.iloc[-1] = 0.0`. No MTM phantom in terminal equity.
- R15. Every in-tree component converted to allocation-native output in the same migration PR.
- R16. `simulate_portfolio` / `simulate_portfolio_batch` in `research/aegis_research/portfolios.py` rewritten; `VBT_PORTFOLIO_FACTORY` / `VBT_RESOLVED_SIZE_TYPE` replaced; `_entry_size_frame` / `_candidate_entry_size_frame` removed.
- R17. Tests asserting entries/exits multi-asset semantics removed; public docs rewritten so target allocation is the only multi-asset contract.

**Origin actors:** A1 (components), A2 (portfolio policy), A3 (portfolio runner), A4 (optimization runner), A5 (config validator), A6 (diagnostics/reporting).

**Origin flows:** F1 (single-portfolio simulation), F2 (multi-candidate batched simulation), F3 (component registration).

**Origin acceptance examples:** AE1 (NaN persistence), AE2 (zero row closes), AE3 (active → allocations), AE4 (full liquidation under shared cash), AE5 (candidate grouping), AE6 (split-gap masking + terminal-row-set-to-zero before PFO), AE7 (registration rejects entries shape), AE8 (diagnostics shape). AE2/AE6 semantics updated for close-execution + terminal liquidation per R5/R8.

---

## Scope Boundaries

- No `pf_method="from_signals"` in v1 (dynamic-signal compilation cost).
- No `vbt.PFO.from_pypfopt`, `from_riskfolio`, `from_universal_algo`, `from_optimize_func`, `from_allocate_func` in v1.
- No `open_to_close` execution policy. No sub-bar ordered open/close rows.
- No `portfolio.min_rebalance_size` / inertia. No drift-threshold rebalancing.
- No `price="nextopen"` / `price="open"` execution alternatives. No opt-in `force_terminal_flat` flag — terminal liquidation is the single forward path.
- No runtime `allocation_mode` choice, no `entries`/`exits` adapter, no opt-in legacy path, no dual-name period for `entry_budget → target_exposure_cap`.
- Components do not own portfolios, official metrics, or arbitrary VBT kwargs.
- No Nautilus runtime adapter for target weights.

### Deferred to Follow-Up Work

- Coordinated update to `docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md` U2/U5 dependency notes (remove the "concurrent landing" hedge). Documentation-only edit, handled out of this PR's commit boundary.

---

## Context & Research

### Relevant Code and Patterns

- **Portfolio runtime** — `research/aegis_research/portfolios.py` (~550 lines, self-contained): `simulate_portfolio` (L42), `simulate_portfolio_batch` (L101), `_entry_size_frame` (L387), `_candidate_entry_size_frame` (L395), `_simulation_signals` (L344), `_next_open_executable_mask` (L443), `_terminal_row_mask` (L463), `_broadcast_mask` (L470), `_execution_timing_kwargs` (L252), `_portfolio_diagnostics` (L281), `_sizing_summary` (L422), `PortfolioSimulationResult` (L37), `expand_market_frame_to_candidate_columns` (L187). Module-level constants `VBT_PORTFOLIO_FACTORY` (L13), `VBT_RESOLVED_SIZE_TYPE` (L14), `PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION` (L12), `SYMBOL_LEVEL` (L11), `VBT_SHARED_CASH_SETTINGS` (cash_sharing=True, group_by=True, call_seq="auto"), `VBT_CANDIDATE_GROUP_BY = "except_level:symbol"`.
- **Portfolio runtime callers** — `research/aegis_research/optimization/runner.py:50,290,305` (`_evaluate_cv_slice`, scalar only); tests at `tests/integration/research/aegis_research/test_portfolios.py` and `tests/unit/research/aegis_research/test_reports.py`. No CLI/strategy-runs/run-splits callers.
- **Component registry** — `research/aegis_research/component_registry/contracts.py:56` (`StrategyManifest.signal_outputs: tuple[str, ...]`); `manifests.py:26` (`STRATEGY_SIGNAL_OUTPUTS = {"entries", "exits"}`); `manifests.py:27` (`STRATEGY_FORBIDDEN_KEYS` blocks `costs, direction, entry_budget, execution_timing, fees, portfolio, portfolio_config, size, sizing, slippage`); `manifests.py:187` (`_strategy_manifest`); `manifests.py:197` (assertion `set(signal_outputs) == {"entries", "exits"}` — choke point); `registry.py:115` (serializer).
- **Portfolio config** — `research/aegis_research/configuration/schema.py:165-171` (`PortfolioConfig`: `init_cash`, `fees`, `slippage`, `entry_budget: float = 1.0`, `direction: str = "longonly"`); `schema.py:14-20` (`PORTFOLIO_TARGET_SIZE_TYPES`, `PORTFOLIO_DIRECTIONS = {"longonly"}`); `validation.py:62-70,838-887` (`_validate_portfolio`).
- **Optimization runner** — `research/aegis_research/optimization/runner.py:304,317` (`_coerce_pipeline_signals` extracts `(entries, exits)` from pipeline output — the entry point that must learn allocation-native shapes).
- **Strategy component** — `research/components/strategies/local_trend_filter.py:88-105`: computes `score`, cross-sectional `rank`, `selected` boolean (an `active` mask), then collapses to `entries`/`exits`. Conversion is unwinding the collapse.

### Institutional Learnings

- `docs/solutions/best-practices/vectorbt-weights-from-signals-vs-orders-2026-05-17.md` — confirms the substrate switch: pure target weights belong in `from_orders`/`from_optimizer` with `targetpercent`, not `from_signals(valuepercent)`.
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md` — direct template for this migration. Pattern: removed config keys fail as *unknown fields* via dataclass-field-set validation; separate `vbt_settings` (active) from `not_applicable_vbt_settings` (diagnostic-only); representative test `test_removed_<field>_fails_as_unknown_field` as the rename gate.
- `docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md` — template for the component output contract: trusted registration, frozen registry snapshot, declared output channel persisted in artifacts.
- `docs/solutions/best-practices/vectorbt-execution-timing-nextopen-2026-05-17.md` — execution timing semantics (historical context; v1 uses default close).
- `docs/solutions/best-practices/vectorbt-close-optimizer-positions-at-end-2026-05-17.md` — `close_at_end` is not supported on `from_optimizer`. Maintainer's blessed terminal-liquidation pattern: `allocations.iloc[-1] = 0` under default `price="close"`. **This plan adopts that pattern exactly via U1's masking layer.** Empirically verified.
- `docs/solutions/logic-errors/vectorbt-allocation-column-alignment-2026-05-17.md` — pandas 2.2 reorders columns alphabetically through empty-frame ops. Reindex every component's output to `close.columns` and `.equals` assert as a hard precondition inside policy validation.
- `docs/solutions/best-practices/vectorbt-targetpercent-nocash-rejections-2026-05-17.md` — `call_seq="auto"` sequences orders but does not synthesize cash. Diagnostics should surface `pf.orders.records_readable` / `pf.logs.records_readable` rejection counts (NoCash especially).
- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md` — `ConfigValidationIssue(path, message)` pattern for fail-fast unknown-field rejection.
- `docs/solutions/performance-issues/vectorbt-large-from-signals-chunking-memory-2026-05-17.md` — `mono_chunk_len`, `chunked=dict(engine="threadpool", chunk_len=...)`, `max_order_records` knobs. Composes with the optimization performance plan; not added in this PR.

### External References

- VBT PRO `PFO.from_filled_allocations` (`.venv/lib/python3.12/site-packages/vectorbtpro/portfolio/pfopt/base.py:2755`): **defaults `valid_only=True, nonzero_only=True, unique_only=True`**. Two of these defaults are wrong for our contract — must pass `nonzero_only=False` (so all-zero target rows close positions) and `unique_only=False` (so consecutive identical target rows are honored).
- VBT PRO `Portfolio.from_optimizer` (`portfolio/base.py:6011`): defaults `pf_method="from_orders"`, `size_type="targetpercent"`, `cash_sharing=True`, `call_seq="auto"`, `fill_value=np.nan`. Direction auto-inference (any-positive → longonly, mixed → both, negative → shortonly) overridden by explicit `direction="longonly"`.
- VBT PRO `price="nextopen"` lowering (`portfolio/preparing.py:1095-1141`): lowered to `price=Open` + `from_ago=1`; last bar's target has no executable next bar and is dropped. **v1 does not use `nextopen` — default `price="close"` only.** Kept here as context for the historical decision.
- VBT PRO `vbt.ExceptLevel("symbol")` (`base/indexes.py:40`): expects column MultiIndex with a level literally named `"symbol"`. Matches existing `SYMBOL_LEVEL` constant.
- VBT PRO `pfo.alloc_records` is `AllocPoints` for `from_filled_allocations`; `pfo.allocations` is the rebalance-row-only DataFrame; `pfo.filled_allocations` is the full date×symbol forward-filled DataFrame.

---

## Key Technical Decisions

- **New package `research/aegis_research/portfolio_policy/`**: cleanly separates Aegis-owned policy concerns from the thin runtime in `portfolios.py`. Resolves the brainstorm's `Deferred to Planning` question on policy module placement. *Alternative considered: keep policy and masking helpers inside `portfolios.py`, or split `portfolios.py` into a `portfolios/` package. Rejected because (a) the package mirrors existing Aegis multi-file conventions (`configuration/schema.py` + `validation.py`, `component_registry/contracts.py` + `manifests.py`), (b) policy and runtime have different actors (A2 vs A3 in the origin), and (c) the masked allocations frame is the boundary value the runtime consumes — placing masking pre-PFO under `portfolio_policy/` matches the conceptual ownership.*
- **Split-aware masking lives in `portfolio_policy/masking.py`**, callable from both single and batch runtime paths and from the policy module if needed. Generalized to operate on an allocations frame (date × symbol or date × (candidate × symbol)) producing the same frame with non-executable rows set to NaN. Resolves the brainstorm's `Deferred to Planning` question on masking placement.
- **`from_filled_allocations(allocations, nonzero_only=False, unique_only=False, valid_only=True)`**: explicit deviation from VBT defaults. Honors the contract that "0.0 row closes positions" and "consecutive identical target rows are real rebalances." `valid_only=True` retained (all-NaN rows = no rebalance, which is correct). *Rationale for `unique_only=False`: components own rebalance cadence — a component that emits a target every bar means rebalance every bar (continuous target exposure, per R1's framing). Silent dedupe at the substrate would mask exactly the turnover behavior diagnostics are meant to expose. Components that want to rebalance only on change emit NaN on unchanged rows. The `pfo.alloc_records` rebalance count in diagnostics surfaces unintended turnover.*
- **`from_optimizer(..., pf_method="from_orders", size_type="targetpercent", direction="longonly", cash_sharing=True, call_seq="auto")` with default `price="close"`**: every value passed explicitly except `price`, which we leave at VBT's default (`"close"`) to match the dominant cross-sectional target-allocation pattern. **Decided after deeper VBT research and empirical testing**: `nextopen` is the less common choice in the VBT community and creates a terminal-handling gap that the maintainer himself flags as unsolved ("could be a useful feature request"). The dominant pattern (`from_orders` + default close + `iloc[-1]=0` terminal liquidation) is verified across the official cookbook, public Discord notebooks (`top10_nasdaq100_v2`), and the maintainer's blessed terminal-handling answer. Adopting it gives clean terminal liquidation, simpler diagnostics, and parity with the broader VBT user base.
- **Terminal liquidation enforced as the single forward path**: `portfolio_policy/masking.py` sets `allocations.iloc[-1] = 0.0` for every symbol that would otherwise hold a position into the terminal bar. Empirically verified (`vbt.run_code`, 2026-05-22): produces cash-realized terminal equity (no MTM phantom), trades complete, downstream metrics work on a clean realized state. No opt-out; no `force_terminal_flat` config flag.
- **`vbt.ExceptLevel(SYMBOL_LEVEL)` for batch, `True` for scalar**: candidate identity flows through PFO's column hierarchy. Use the existing `SYMBOL_LEVEL` constant verbatim — VBT's `ExceptLevel` matches by literal level name.
- **Reindex assertion at policy boundary**: every component output is reindexed to `close.columns` and asserted `.equals(close.columns)` inside the policy module. Defense against pandas 2.2 alphabetical column reorder (solutions library finding).
- **Forward-first rename pattern via unknown-field rejection**: `portfolio.entry_budget` removed from `PortfolioConfig` and rejected as an *unknown field* in `_validate_portfolio`, mirroring `forward-first-long-only-signal-contract` (solutions library template). Representative test `test_removed_entry_budget_field_fails_as_unknown_field`.
- **`signal_outputs` field renamed to `output_name` (singular)** on `StrategyManifest`. One declared shape per component. Component registry enforces membership in `STRATEGY_ALLOCATION_OUTPUTS = {"active", "scores", "ranks", "target_weights"}`; rejects {entries, exits}.
- **All four shapes registrable in v1 via the implicit-from-non-NaN contract.** A component selects symbols by emitting non-NaN values for the chosen set and NaN for excluded symbols. The policy converts `active`/`scores`/`ranks` to allocations identically — equal-weight on non-NaN cells, scaled to `target_exposure_cap`. `target_weights` passes through directly (validate + reindex). The four shapes differ only in *informational content*: `active` carries a bool mask, `scores` carries the underlying score, `ranks` carries the ordinal rank, `target_weights` carries explicit weights. Top-N is owned by the component (it decides what to NaN out). No `top_n` config field at the policy level. VBT does not provide a built-in top-N primitive — every VBT user reinvents it; this contract centralizes the convention so Aegis components share one shape across multiple scoring strategies.
- **`local_trend_filter` converts to `active` shape**: its internal `selected` boolean mask is already an active mask; declaring `active` is the smallest delta from current behavior. Top-N is already baked into `selected`.
- **No same-bar lookahead opt-in.** Single forward path is close-decision, close-execution. If a future research workflow requires strict no-lookahead semantics, that's a separate substrate decision (own brainstorm) — not a v1 config flag.
- **Diagnostics schema bumps to `portfolio_diagnostics.v3`**. Legacy fields (`allocation_mode: "event_style_signals"`, `rebalances_existing_positions: False`, `entry_budget`, sizing.min/max_nonzero_valuepercent, raw_signals/simulation_signals entries-keyed blocks) removed. New fields include `factory: "Portfolio.from_optimizer"`, `pf_method: "from_orders"`, `size_type: "targetpercent"`, `target_exposure_cap`, `rebalance_rows` (from `pfo.alloc_records`), `allocations` (from `pfo.allocations` — sparse rebalance-row-only), `realized_at_fill` (per-rebalance-row realized weights from `pf.assets`), `order_rejection_counts` (from `pf.logs.records_readable`), `non_executable` (split-gap counts), `execution_timing="close"`, `terminal_liquidation=True`. `not_applicable_vbt_settings` block retained for diagnostic-only fields.
- **Optimization performance plan ordering**: this plan is a hard prerequisite to plan #002's U2/U5. Plan #002's "concurrent landing" hedge is superseded; documentation-only update to that plan is deferred to follow-up.

---

## Open Questions

### Resolved During Planning

- *Where does the policy module live?* — New package `research/aegis_research/portfolio_policy/` with `policy.py` (component output → allocations) and `masking.py` (split-aware masking). Resolves brainstorm Deferred to Planning #1.
- *Where does split-aware masking live?* — `portfolio_policy/masking.py`, called by both runtime paths and re-exported through the package. Resolves brainstorm Deferred to Planning #2.
- *How is candidate identity encoded in the wide allocations frame?* — Reuse existing `SYMBOL_LEVEL` constant and `expand_market_frame_to_candidate_columns` (`portfolios.py:187`) which already produces MultiIndex columns with a `symbol` level. `vbt.ExceptLevel(SYMBOL_LEVEL)` groups by all non-symbol levels (candidate id). No new column hierarchy needed. Resolves brainstorm Deferred to Planning #3.
- *Diagnostic payload schema shape?* — Schema bump to v3, fields enumerated in Key Technical Decisions. `not_applicable_vbt_settings` slot reused. Realized-vs-requested comparison structured as date × symbol per rebalance row, scoped per candidate via `pfo.alloc_records`. Resolves brainstorm Deferred to Planning #4.
- *Component / test inventory for migration?* — One strategy component (`local_trend_filter`). Test files enumerated in Context section. Resolves brainstorm Deferred to Planning #5.
- *Out-of-tree `entry_budget` consumers?* — No CLI, run_splits, or strategy_runs callers reference `entry_budget` outside the runtime and tests. Test fixtures at `tests/support/research/aegis_research/run_config_fixtures.py` are the only other usage. Resolves brainstorm Deferred to Planning #6.

### Deferred to Implementation

- Final method signatures inside `portfolio_policy/policy.py` (one dispatcher function vs. per-shape functions). Either shape is acceptable; the choice surfaces during implementation. Test surface is defined regardless.
- Exact `realized_vs_requested` payload structure (per-rebalance-row JSON vs. flat DataFrame). Resolve during diagnostics implementation while looking at downstream report consumers.
- Whether `non_executable` diagnostics need re-keying when wrapped per-candidate vs. per-symbol. Resolve while implementing U2/U3.
- `target_exposure_cap` upper bound is `1.0` (carried from existing `entry_budget` validation at `validation.py:845` `maximum=1`). Acceptable for v1 longonly; revisit only when a real leveraged-longonly use case emerges.
- Stored on-disk evidence written under `portfolio_diagnostics.v2` will not be re-loadable into v3-aware consumers. The plan ships v3 as a clean break (schema_version mismatch). Re-running historical runs against v1 is the path.
- `unique_only=False` is the substrate contract. If research patterns later produce too many redundant rebalances, the component owns dedupe by emitting NaN on unchanged rows (the existing `local_trend_filter` pattern via its `rebalance` mask).

---

## Output Structure

```text
research/aegis_research/portfolio_policy/
├── __init__.py                  # re-exports: convert_to_allocations, apply_executable_mask
├── policy.py                    # component output → validated allocations frame
└── masking.py                   # split-aware executable masking on allocations frames

research/aegis_research/portfolios.py                       # rewritten — thin PFO substrate runtime
research/aegis_research/configuration/schema.py             # PortfolioConfig: entry_budget → target_exposure_cap
research/aegis_research/configuration/validation.py         # _validate_portfolio: unknown-field rejection of entry_budget
research/aegis_research/component_registry/contracts.py     # StrategyManifest.signal_outputs → output_name
research/aegis_research/component_registry/manifests.py     # STRATEGY_SIGNAL_OUTPUTS → STRATEGY_ALLOCATION_OUTPUTS (v1: {active, target_weights})
research/aegis_research/component_registry/registry.py      # serializer + _definition_public_snapshot follow-through
research/aegis_research/optimization/runner.py              # _coerce_pipeline_signals → _coerce_pipeline_output
research/aegis_research/optimization/source.py              # docstring rename
research/components/strategies/local_trend_filter.py        # emits active instead of entries/exits

research/configs/component_ma_cross_dry_run.yaml            # entry_budget → target_exposure_cap
research/configs/local_component_e2e.yaml                   # entry_budget → target_exposure_cap

tests/integration/research/aegis_research/test_portfolios.py        # U8 — rewritten contract tests
tests/integration/research/aegis_research/test_portfolio_policy.py  # U1 (scaffold) + U8 (impls) — new
tests/unit/research/aegis_research/test_reports.py                  # U8 — v3 diagnostics shape
tests/unit/research/aegis_research/test_component_registry.py       # U8 — output_name contract

tests/integration/research/aegis_research/test_config_contract.py   # U10 — entry_budget rejection
tests/integration/research/aegis_research/test_lane_config_contract.py # U10

tests/integration/research/aegis_research/test_cli.py               # U11 — fixture cascade
tests/integration/research/aegis_research/test_strategy_run.py      # U11 — fixture cascade
tests/integration/research/aegis_research/test_run_playbook_sources.py # U11
tests/support/research/aegis_research/run_config_fixtures.py        # U11 — target_exposure_cap
tests/support/research/aegis_research/component_fixtures.py         # U11 — output_name declarations

tests/unit/research/aegis_research/test_optimization_component_source.py # U12
tests/unit/research/aegis_research/test_optimization_candidate_store.py  # U12
tests/unit/research/aegis_research/test_optimization_evidence.py         # U12
tests/unit/research/aegis_research/test_optimization_execute_validation.py # U12
tests/unit/research/aegis_research/test_optimization_promotion.py        # U12
tests/unit/research/aegis_research/test_optimization_failure_paths.py    # U12 (verify need)

docs/components.md                                          # target-allocation contract
docs/vectorbt-scaffold.md                                   # PFO substrate, targetpercent, no entry_budget
```

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

Forward path (scalar and batched share the same shape):

```text
strategy/alpha component
        │  emits one declared output:
        │    scores | ranks | active | target_weights
        │  (non-NaN cells = selected this rebalance; NaN = excluded)
        ▼
portfolio_policy.policy.convert_to_allocations(
    output, declared_shape, *,
    close_columns, target_exposure_cap, direction="longonly",
)                                                          # validates: longonly, sum ≤ cap, no dupes,
        │                                                  # reindexed .equals(close.columns)
        ▼  allocations frame: date × symbol, NaN = no rebalance, 0.0 = real target
portfolio_policy.masking.apply_executable_mask(
    allocations, *, market_index,
)                                                          # split-gap rows → NaN; terminal row → 0.0 (liquidation)
        │                                                  # returns (allocations_masked, non_exec_diag)
        ▼
vbt.PFO.from_filled_allocations(
    allocations_masked,
    valid_only=True,
    nonzero_only=False,        # 0.0 row must close, not be dropped
    unique_only=False,         # consecutive identical targets are real rebalances
)
        ▼
vbt.Portfolio.from_optimizer(
    close, pfo,
    pf_method="from_orders",
    size_type="targetpercent",
    direction="longonly",
    cash_sharing=True,
    call_seq="auto",
    group_by=True | vbt.ExceptLevel(SYMBOL_LEVEL),
    # default price="close" — no kwarg passed
    fees=..., slippage=..., init_cash=...,
)
        ▼
PortfolioSimulationResult(portfolio=pf, diagnostics=v3 payload)
```

Diagnostics v3 sources:
- `pf.orders.records_readable` / `pf.logs.records_readable` → order rejection counts (NoCash, PartialFill, SizeNaN, SizeZero).
- `pfo.alloc_records` (AllocPoints for `from_filled_allocations`) → rebalance row idx + candidate column.
- `pfo.allocations` → rebalance-row-only DataFrame (requested).
- `pfo.filled_allocations` → full date×symbol DataFrame (forward-filled requested).
- `pf.assets` at rebalance row idx → realized allocation for `realized_vs_requested`.
- Split-gap diagnostics → `non_executable` block. Terminal liquidation → `contract.terminal_liquidation = True` + the terminal row appears in `rebalance_rows` as a 0.0 sell.

---

## Implementation Units

- [ ] U1. **Build `portfolio_policy/` package: masking + component-output conversion**

**Goal:** Establish the Aegis-owned policy layer that converts component output to a validated allocations frame and applies split-aware executable masking. Foundation for the runtime rewrite.

**Requirements:** R2, R3, R4, R6, R8.

**Dependencies:** None.

**Files:**
- Create: `research/aegis_research/portfolio_policy/__init__.py`
- Create: `research/aegis_research/portfolio_policy/policy.py`
- Create: `research/aegis_research/portfolio_policy/masking.py`
- Test: `tests/integration/research/aegis_research/test_portfolio_policy.py`

**Approach:**
- `policy.py` exports `convert_to_allocations(component_output, declared_shape, *, close_columns, target_exposure_cap, direction="longonly") -> pd.DataFrame`. Dispatches on `declared_shape`:
  - `"target_weights"`: validate longonly (no negatives), gross sum ≤ cap per row, no duplicate symbols, reindex to `close_columns` and assert `.equals`. Return as-is (NaN = no rebalance, 0.0 = real target).
  - `"active"`, `"scores"`, `"ranks"` (unified conversion family — implicit-from-non-NaN): a non-NaN cell means "selected this rebalance row"; NaN means "not selected." For `active`, the value is a bool; for `scores`, a float; for `ranks`, an ordinal. All convert identically: count non-NaN selections per row, divide `target_exposure_cap` evenly across them, emit 0.0 for the NaN cells (so dropouts close), and emit NaN for rows with no non-NaN cells (no rebalance). The shape distinction is preserved in diagnostics for downstream analysis.
  - Unknown shape: raise with the contract-violation message naming the unsupported shape and `STRATEGY_ALLOCATION_OUTPUTS`.
- `masking.py` exports `apply_executable_mask_and_terminal_liquidation(allocations, *, market_index) -> tuple[pd.DataFrame, dict]`. Two responsibilities, single pass:
  1. **Split-aware executability**: non-executable rows due to market-index gaps are set to NaN (no rebalance). 0.0 cells in executable rows pass through (real targets).
  2. **Terminal liquidation**: enforce `allocations.iloc[-1] = 0.0` for every symbol — single forward path, no opt-out. The terminal row becomes a real rebalance to all-zero, which under default `price="close"` executes at the last bar's close and produces a cash-realized terminal. Empirically verified.
- Generalizes the existing `_next_open_executable_mask` and `_terminal_row_mask` from `portfolios.py` but reinterprets the terminal: instead of masking the terminal row to NaN (which was correct under `nextopen` where it had no executable next bar), the new contract WRITES `0.0` to the terminal row so it executes at close.
- Wide-frame (multi-candidate) support: masking + terminal liquidation apply per-candidate-column-group; broadcast pattern follows existing `_broadcast_mask` semantics.
- Reindex assertion uses `.equals(close.columns)` for ordering + dtype safety against pandas 2.2 alphabetical column reorder (solutions library finding).

**Patterns to follow:**
- Forward-first contract pattern from `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`.
- Reindex-and-assert from `docs/solutions/logic-errors/vectorbt-allocation-column-alignment-2026-05-17.md`.
- Existing masking implementations at `research/aegis_research/portfolios.py:443-470` (lift, do not reinvent).

**Test scenarios:**
- Happy path: `target_weights` shape with valid frame returns identical frame after reindex.
- Happy path: `active` shape `{A: True, B: True, C: False}` row under `target_exposure_cap=1.0` returns `{A: 0.5, B: 0.5, C: 0.0}`. **Partially covers AE3** (policy conversion step; full end-to-end PFO flow verified in U2/U8).
- Happy path: `scores` shape with `{A: 1.4, B: 0.8, C: NaN}` row under `target_exposure_cap=1.0` returns `{A: 0.5, B: 0.5, C: 0.0}` — non-NaN cells equal-weighted; C closes.
- Happy path: `ranks` shape with `{A: 1, B: 2, C: NaN, D: NaN}` row under `target_exposure_cap=0.8` returns `{A: 0.4, B: 0.4, C: 0.0, D: 0.0}` — non-NaN cells equal-weighted.
- Happy path: `active`/`scores`/`ranks` row of all-NaN passes through as NaN row (no rebalance).
- Edge case: empty selection in `active` (all False) returns all-0.0 row (closes positions).
- Edge case: empty selection in `scores`/`ranks` (all NaN) → no rebalance on that row (output row is all NaN, not all 0.0; the policy distinguishes "no decision" from "decision to be flat").
- Edge case: column reordered relative to `close.columns` → reindex restores ordering; symbol mismatch raises with the mismatched symbol(s) named.
- Error path: `target_weights` row with negative value → validation error citing the longonly constraint.
- Error path: `target_weights` row with sum > `target_exposure_cap` → validation error citing the cap.
- Error path: declared shape not in `STRATEGY_ALLOCATION_OUTPUTS` (e.g., `"entries"`, `"momentum"`) → validation error citing the contract.
- Edge case (terminal liquidation): the terminal row of the output is `0.0` for every symbol (overwriting any prior content). Diagnostic records that terminal liquidation was applied. **Covers AE6.**
- Edge case (masking): split-gap row → masked to NaN; non-executable diagnostic incremented.
- Edge case (masking): 0.0 row in a non-terminal, non-gap location passes through unchanged. **Covers AE2 (preserved for U2 to assert end-to-end).**
- Edge case (masking): NaN row passes through unchanged (except terminal — always overwritten to 0.0).
- Edge case (masking): wide multi-candidate frame masked + terminally-liquidated per candidate; one candidate's gap row does not affect another candidate; terminal liquidation applies to every candidate independently.

**Verification:**
- `pytest tests/integration/research/aegis_research/test_portfolio_policy.py` passes.
- Importing `portfolio_policy` exposes only `convert_to_allocations` and `apply_executable_mask`.

---

- [ ] U2. **Rewrite `simulate_portfolio` and `simulate_portfolio_batch` on PFO substrate**

**Goal:** Replace the `from_signals(valuepercent)` substrate with `PFO.from_filled_allocations(...)` + `Portfolio.from_optimizer(..., pf_method="from_orders")`. Both scalar and batched paths share the same forward shape; only `group_by` differs.

**Requirements:** R1, R5, R6, R7, R9, R10, R16.

**Dependencies:** U1.

**Files:**
- Modify: `research/aegis_research/portfolios.py`
- Test: `tests/integration/research/aegis_research/test_portfolios.py` (rewritten in U8)

**Approach:**
- New signatures: `simulate_portfolio(close, allocations, config, *, market_index)` and `simulate_portfolio_batch(close_wide, allocations_wide, config, *, market_index)`. Inputs are validated allocations frames (output of U1's `convert_to_allocations`). **`open_prices` is no longer a runtime parameter** — close execution does not need an open frame.
- Apply U1's `apply_executable_mask_and_terminal_liquidation` to the allocations frame before PFO. The masking layer enforces terminal liquidation (`iloc[-1] = 0.0` for every symbol) so the substrate produces a cash-realized terminal under default `price="close"`.
- Build PFO: `vbt.PFO.from_filled_allocations(masked, valid_only=True, nonzero_only=False, unique_only=False)`.
- Build portfolio: `vbt.Portfolio.from_optimizer(close_for_pfo, pfo, pf_method="from_orders", size_type="targetpercent", direction="longonly", cash_sharing=True, call_seq="auto", group_by=True for scalar / vbt.ExceptLevel(SYMBOL_LEVEL) for batch, fees=config.fees, slippage=config.slippage, init_cash=config.init_cash, freq=...)`. **No `price` kwarg — default `"close"` is the contract.**
- **Close-frame shape for batch path**: PFO's `from_optimizer` forwards `close` to `from_orders` as-is and `from_orders` broadcasts against the wide allocations columns. Pre-expand `close` via the existing `expand_market_frame_to_candidate_columns` helper for safety against pandas 2.2 column-reorder surprises. The batch path already pays the expansion cost today; keep it.
- Update module-level constants: `VBT_PORTFOLIO_FACTORY = "Portfolio.from_optimizer"`, `VBT_RESOLVED_SIZE_TYPE = "targetpercent"`. Add `VBT_PF_METHOD = "from_orders"`.
- Remove: `_entry_size_frame`, `_candidate_entry_size_frame`, `_simulation_signals`, `_validate_signal_frames`, `_validate_candidate_signal_frames` (replaced by policy-side validation), `_sizing_summary`, the `entry_budget` branch of `_execution_timing_kwargs`.
- Keep: `PortfolioSimulationResult`, `SYMBOL_LEVEL`, `expand_market_frame_to_candidate_columns`, `_validate_candidate_columns`, `portfolio_record_counts`. Split-gap + terminal-liquidation helpers move into `portfolio_policy/masking.py` per U1. `_execution_timing_kwargs` and related `nextopen`/`open_prices` plumbing is removed entirely — close execution does not need it.

**Patterns to follow:**
- VBT `from_optimizer` kwarg ordering from external research findings (every value explicit; do not rely on inference).
- Existing batch wide-frame handling from `expand_market_frame_to_candidate_columns` (`portfolios.py:187`).

**Test scenarios:** (full contract coverage lives in U8; U2 ships with smoke-test scenarios in `test_portfolios.py`)
- Happy path: single-portfolio with two-symbol allocations frame + `cash_sharing=True` + `group_by=True` → returns one `vbt.Portfolio` with non-zero trades and **cash-realized terminal** (final cash = final equity; no MTM phantom).
- Happy path: batched with three candidates over four symbols + `group_by=vbt.ExceptLevel(SYMBOL_LEVEL)` → one `vbt.Portfolio` with candidate-grouped trades; each candidate-group ends cash-realized.
- Happy path (batched): `pfo.allocations` after `column_stack` of three candidates preserves the candidate level in its column MultiIndex; `pfo.alloc_records.col_arr` distinguishes candidates. **Covers AE5.**
- Edge case: NaN allocations row → no rebalance at that row. **Covers AE1.**
- Edge case: all-0.0 allocations row in a non-terminal location → closes existing positions at that bar's close (confirms `nonzero_only=False` is correctly passed). **Covers AE2.**
- Edge case: consecutive identical target rows under `unique_only=False` → both rebalance rows appear in `pfo.alloc_records`.
- Edge case: full-A → full-B switch under shared cash → A sold down, B bought at the same bar's close. **Covers AE4.**
- Edge case (terminal liquidation): a run with a long position held into the last bar → final cash equals final equity; final assets per symbol = 0; the terminal row appears in `pfo.alloc_records` as a sell.

**Verification:**
- Module no longer imports `vbt.Portfolio.from_signals`.
- `simulate_portfolio` / `simulate_portfolio_batch` callable shapes match the new signatures.

---

- [ ] U3. **Diagnostics v3: PFO-native fields, schema version bump, NoCash surfacing**

**Goal:** Replace the v2 diagnostics payload with a v3 schema sourced from PFO + `vbt.Portfolio` accessors, recording everything the brainstorm enumerates.

**Requirements:** R13, R14.

**Dependencies:** U2, U6 (reads `config.target_exposure_cap` field renamed in U6).

**Files:**
- Modify: `research/aegis_research/portfolios.py` (`_portfolio_diagnostics`, `PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION`)

**Approach:**
- Bump `PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION = "portfolio_diagnostics.v3"`.
- Remove fields: `contract.allocation_mode`, `contract.entry_budget`, `contract.entry_budget_interpretation`, `contract.rebalances_existing_positions`, `sizing` (entire block including min/max_nonzero_valuepercent), `raw_signals`, `simulation_signals`.
- Add fields under existing top-level blocks:
  - `vbt_settings.factory = "Portfolio.from_optimizer"`, `vbt_settings.pf_method = "from_orders"`, `vbt_settings.size_type = "targetpercent"`, `vbt_settings.group_by = "all_symbols_single_group" | "except_level:symbol"`.
  - `contract.target_exposure_cap = config.target_exposure_cap`.
  - `contract.execution_timing = "close"` (close-decision, close-execution; default VBT pattern).
  - `contract.terminal_liquidation = True` (always; single forward path).
  - New top-level `allocations` block:
    - `rebalance_rows`: list of (date, candidate-id-or-null) tuples from `pfo.alloc_records.get_field_arr("alloc_idx")` + `col_arr`. (VBT field is `alloc_idx`, not `idx`; verified in `vectorbtpro/portfolio/enums.py:3511-3518`.)
    - `requested`: serializable dump of `pfo.allocations` (rebalance-row-only — sparse, ~one row per rebalance).
    - `realized_at_fill`: per-rebalance-row realized weights at fill, sourced from `pf.assets` at the rebalance row idx joined back per candidate via `alloc_records.col_arr`. Scope: rebalance rows only (sparse), not the full forward-filled frame. **Dropped from R13 interpretation: the full `pfo.filled_allocations` forward-filled dump and the unbounded `realized_vs_requested` per-cell comparison — both were unbounded payloads for fields no current in-tree consumer reads (verified: optimization runner discards `result.diagnostics` at `runner.py:314`; `reports.py` reads from `pf` directly).** The sparse `requested` + `realized_at_fill` pair on rebalance rows satisfies R13's intent ("realized allocation at rebalance fill rows compared against the requested allocation") without the cost of a full date×symbol dump per run.
  - New top-level `order_rejections` block: counts from `pf.logs.records_readable` keyed by status (`NoCash`, `PartialFill`, `SizeNaN`, `SizeZero`). Surfaces the solutions library finding on `targetpercent` NoCash rejections.
  - `non_executable`: split-gap counts preserved from U1's masking diagnostic dict. (Terminal row is no longer "non-executable" — it's a liquidation rebalance.)
- Retain: `not_applicable_vbt_settings` slot for diagnostic-only fields (mirrors the forward-first-long-only-signal-contract template).

**Patterns to follow:**
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md` — separate `vbt_settings` (active) from `not_applicable_vbt_settings` (diagnostic-only); representative test conventions.
- `docs/solutions/best-practices/vectorbt-targetpercent-nocash-rejections-2026-05-17.md` — order rejection surfacing.

**Test scenarios:**
- Happy path: v3 payload contains every field enumerated in R13; legacy fields absent. **Covers AE8.**
- Happy path: batched run with three candidates produces `rebalance_rows` keyed per-candidate via `alloc_records.col_arr`; candidate identity preserved through PFO column hierarchy. **Covers AE5.**
- Edge case: payload with one rebalance row → `alloc_records`-derived list has length 1.
- Edge case: payload with no rebalance rows (all NaN allocations) → `alloc_records` list is empty; `realized_vs_requested` is empty.
- Edge case: payload with split-gap masked rows → `non_executable` counts populated correctly; PFO did not receive the masked rows as targets. **Covers AE6.**
- Edge case: payload always reports `contract.terminal_liquidation = True` and `contract.execution_timing = "close"`; terminal row appears as a `0.0` rebalance in `rebalance_rows`.
- Edge case: payload with order rejections (force a NoCash via fees > 0 and gross exposure near cap) → `order_rejections.NoCash` > 0.
- Edge case: `schema_version == "portfolio_diagnostics.v3"` and `not_applicable_vbt_settings` does not include any active setting.

**Verification:**
- `pytest -k diagnostics` passes against the new schema.

---

- [ ] U4. **Component registry: allocation-native output contract**

**Goal:** Register the four allocation-native shapes `{active, scores, ranks, target_weights}`. Rename `signal_outputs` to `output_name` (singular). Reject `entries`/`exits` declarations at registration.

**Requirements:** R2, R12.

**Dependencies:** U6 (the `STRATEGY_FORBIDDEN_KEYS` rename below requires U6's portfolio-config rejection path to be in place; land in the same commit).

**Files:**
- Modify: `research/aegis_research/component_registry/contracts.py`
- Modify: `research/aegis_research/component_registry/manifests.py`
- Modify: `research/aegis_research/component_registry/registry.py`
- Test: `tests/unit/research/aegis_research/test_component_registry.py`

**Approach:**
- `contracts.py`: rename `StrategyManifest.signal_outputs: tuple[str, ...]` to `output_name: str` (singular). Update docstring to reference the four allocation-native shapes.
- `manifests.py`: replace `STRATEGY_SIGNAL_OUTPUTS = {"entries", "exits"}` with `STRATEGY_ALLOCATION_OUTPUTS = {"active", "scores", "ranks", "target_weights"}`. Replace the assertion at line 197 with: `assert manifest.output_name in STRATEGY_ALLOCATION_OUTPUTS, f"unsupported allocation output {manifest.output_name!r}; registered shapes are {STRATEGY_ALLOCATION_OUTPUTS}"`. **Update `STRATEGY_FORBIDDEN_KEYS`: replace `entry_budget` with `target_exposure_cap`** (the rename in U6 changes the field name; the component-cannot-own-portfolio-cap rule remains).
- `registry.py:115`: serializer follows the field rename; `payload["output_name"]` instead of `payload["signal_outputs"]`. `_definition_public_snapshot` (`registry.py:92`) also propagates the new field.
- Component manifests pre-snapshot persist the declared output channel (mirrors model-plugin-target-probability pattern from solutions library).

**Patterns to follow:**
- `docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md` — declared output channel with frozen registry snapshot.

**Test scenarios:**
- Happy path: manifest with `output_name="active"` registers and round-trips through serializer.
- Happy path: manifest with `output_name="target_weights"` registers.
- Happy path: manifest with `output_name="scores"` registers.
- Happy path: manifest with `output_name="ranks"` registers.
- Error path: manifest with `output_name="entries"` raises with the contract-violation message naming `STRATEGY_ALLOCATION_OUTPUTS`. **Covers AE7.**
- Error path: manifest with legacy `signal_outputs={"entries", "exits"}` field raises (unknown field).
- Error path: manifest with `output_name="momentum"` (not in the registered shape set) raises citing the contract.
- Edge case: manifest with `output_name` containing `target_exposure_cap` as a forbidden key (component should not own portfolio-level config) fails citing `STRATEGY_FORBIDDEN_KEYS`.

**Verification:**
- Loading the registry with `local_trend_filter`'s updated manifest (U5) succeeds.

---

- [ ] U5. **Convert `local_trend_filter` to allocation-native `active` output**

**Goal:** Migrate the only in-tree strategy component to the new contract. Its internal `selected` boolean mask becomes its declared `active` output.

**Requirements:** R2, R15.

**Dependencies:** U4.

**Files:**
- Modify: `research/components/strategies/local_trend_filter.py`
- Test: existing `tests/integration/research/aegis_research/test_strategy_run.py`, `tests/unit/research/aegis_research/test_optimization_component_source.py`, fixtures at `tests/support/research/aegis_research/component_fixtures.py`

**Approach:**
- Manifest declares `output_name="active"`.
- Internal pipeline at lines 88-105: keep score and rank computation. **Critical: the conversion is not just `active = selected`. The current code uses `entries = (rebalance & selected).fillna(False)` (line 99) where `rebalance.iloc[::rebalance_every, :] = True` (line 96) gates the rebalance cadence. The new `active` output must preserve that cadence as NaN sentinels on non-rebalance rows; otherwise every bar becomes a real target under `unique_only=False` and the portfolio rebalances every bar.**
- Dtype contract for `active` shape: **object or float**, not bool, because the contract must encode three states per cell: True (active on this rebalance row), False (inactive on this rebalance row, target = 0.0), NaN (no rebalance decision on this row). Bool dtype cannot encode the third state. U1's `convert_to_allocations("active", ...)` must accept this dtype.
- Concrete conversion: emit `active = pd.DataFrame(np.nan, index=close.index, columns=close.columns).where(...)` then `active.loc[rebalance_rows] = selected.loc[rebalance_rows]`. On rebalance rows, True/False values from `selected`. Off rebalance rows, NaN (= no rebalance, per policy contract).
- Remove the entries/exits collapse code at lines 99-105.
- Coordinate with U1: U1's `active` shape handler must accept object/float dtype with NaN sentinels; the test scenario "all-False row → all-0.0 row" still applies for rebalance rows where the active set is empty.

**Patterns to follow:**
- The existing `selected` computation as the natural `active` shape.

**Test scenarios:**
- Happy path: running `local_trend_filter` returns an active mask DataFrame matching `close.columns`.
- Happy path: routed through `portfolio_policy.convert_to_allocations(..., "active", ...)` produces an equal-weight allocations frame as in AE3. **Covers F1, AE3.**
- Edge case: a date where no symbol is selected yields an all-False row → policy converts to all-0.0 (closes everything).
- Integration: a full `simulate_portfolio` run with the converted component matches the AE4 full-liquidation behavior.

**Verification:**
- `pytest tests/integration/research/aegis_research/test_strategy_run.py` passes against the new shape.

---

- [ ] U6. **Rename `portfolio.entry_budget` → `portfolio.target_exposure_cap`; unknown-field rejection**

**Goal:** Forward-first rename of the portfolio config field with no dual-name period; legacy name fails as an unknown field. Cascades to YAML config fixtures and any in-tree docstring referencing the old name.

**Requirements:** R11, R12.

**Dependencies:** None (parallel with U1).

**Files:**
- Modify: `research/aegis_research/configuration/schema.py`
- Modify: `research/aegis_research/configuration/validation.py`
- Modify: `research/aegis_research/optimization/source.py` (docstring at line 11 references `entry_budget`)
- Modify: `research/configs/component_ma_cross_dry_run.yaml` (literal `entry_budget: ...`)
- Modify: `research/configs/local_component_e2e.yaml` (literal `entry_budget: ...`)
- Test: covered by U10 (config rejection tests)
- Modify: `tests/support/research/aegis_research/run_config_fixtures.py`

**Approach:**
- `schema.py:165-171`: rename `entry_budget: float = 1.0` to `target_exposure_cap: float = 1.0`. Keep `init_cash`, `fees`, `slippage`, `direction`.
- `validation.py` (`_section` at L62-67 and `_validate_portfolio` at L838-887): the existing `_section` allowed-fields set is `set(PortfolioConfig.__dataclass_fields__) | {"size", "size_type"}` — once `entry_budget` leaves the dataclass, `_section` will emit a generic "unknown field" error before `_validate_portfolio` runs, so the planned "renamed to" message would be masked. **Resolve by extending `_section`'s allowed set to include `"entry_budget"` as a deprecated-with-message key**, then have `_validate_portfolio` intercept it and emit `ConfigValidationIssue("portfolio.entry_budget", "renamed to portfolio.target_exposure_cap")`. Alternative shape: introduce a `_removed_fields` mapping `{"entry_budget": "renamed to portfolio.target_exposure_cap"}` consulted by `_section` before unknown-field rejection. Either is acceptable; the implementer chooses, but the wiring must be explicit so the rename message actually fires.
- `_validate_portfolio` body: add `target_exposure_cap` check (must be `> 0`, `≤ 1.0`; default upper bound mirrors the existing `entry_budget` validation at `validation.py:845` `maximum=1`). Note: the 1.0 ceiling forecloses leveraged-longonly research scenarios; surfaced in Open Questions for future revisit.
- Keep rejection of `portfolio.size`, `portfolio.size_type`, and the existing direction/cash rules.
- Update `run_config_fixtures.py` to emit `target_exposure_cap` instead of `entry_budget`.
- Note for downstream coordination: `docs/profiling/2026-05-22-aerd-run-cprofile.md` references `research/configs/local_component_e2e.yaml` by path as the canonical profiling baseline. Plan #002 also references it. Renaming the field in this YAML breaks reproducibility of the historical profile against `main`. Either (a) update the profiling artifact to note that pre-migration baselines require a git-revert of the YAML, or (b) duplicate the legacy YAML under a date-suffixed name for historical reproducibility, or (c) accept the breakage and document the supersession.

**Patterns to follow:**
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md` — unknown-field rejection pattern.
- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md` — `ConfigValidationIssue(path, message)` shape.

**Test scenarios:** (test implementations live in U10)
- Happy path: config with `portfolio.target_exposure_cap=0.8` validates.
- Error path: config with `portfolio.entry_budget=0.6` fails with `ConfigValidationIssue` whose path is `portfolio.entry_budget` and message references the rename. Representative test name: `test_removed_entry_budget_field_fails_as_unknown_field`.
- Error path: config with `portfolio.size=0.5` continues to fail.
- Error path: config with `portfolio.size_type="valuepercent"` continues to fail.
- Edge case: config with both `entry_budget` and `target_exposure_cap` fails first on `entry_budget` (do not silently take the new name and ignore the legacy).
- Edge case: config with `portfolio.target_exposure_cap` out of `(0, 1]` fails.
- Integration: existing YAML configs (`research/configs/component_ma_cross_dry_run.yaml`, `research/configs/local_component_e2e.yaml`) load and validate with the renamed field.

**Verification:**
- `pytest -k config_contract` passes (test implementations land with U10).
- `grep -r entry_budget research/` returns no matches.

---

- [ ] U7. **Optimization runner: route allocation-native component output through portfolio policy**

**Goal:** Replace `_coerce_pipeline_signals(entries, exits)` extraction with allocation-output extraction. Hand the component's declared output to `portfolio_policy.convert_to_allocations` and pass the resulting allocations frame to `simulate_portfolio`.

**Requirements:** R1, R3.

**Dependencies:** U1 (policy module), U2 (new `simulate_portfolio` signature), U4 (manifest field rename), U5 (`local_trend_filter` converted), U6 (reads `config.target_exposure_cap` when building the policy invocation).

**Files:**
- Modify: `research/aegis_research/optimization/runner.py`
- Modify: `research/aegis_research/optimization/source.py` — extend `OPTIMIZATION_SOURCE_ALLOWED_KEYS` to carry `output_name`; add the field to the `OptimizationSource` dataclass so the runner can read the declared shape post-pipeline-closure.
- Modify: `research/aegis_research/optimization/component_source.py` — thread `definition.manifest.output_name` from the registered `ComponentDefinition` into the returned `OptimizationSource` inside `build_component_optimization_source`.
- Test: `tests/unit/research/aegis_research/test_optimization_component_source.py`, `tests/unit/research/aegis_research/test_optimization_*.py` (impls land in U12)

**Approach:**
- Rename `_coerce_pipeline_signals` to `_coerce_pipeline_output(pipeline_output, declared_shape)`. Returns the raw shape (DataFrame for active/target_weights/scores/ranks).
- Update `_evaluate_cv_slice` (`runner.py:290`) to: extract declared shape from the manifest, extract the raw output, call `convert_to_allocations`, call `simulate_portfolio` with the allocations frame.
- Carry `declared_shape` through any logging / candidate identity so diagnostics record the source shape per candidate.

**Patterns to follow:**
- Existing `_coerce_pipeline_signals` extraction pattern (`runner.py:304,317`) for shape-tolerant access (dict vs tuple).

**Test scenarios:**
- Happy path: optimization runner over `local_trend_filter` produces a candidate-keyed allocations frame and simulates through `simulate_portfolio_batch`.
- Happy path: candidate identity flows from manifest → allocations frame columns → `pfo.alloc_records` → diagnostics. **Covers F2, AE5.**
- Edge case: pipeline output missing the declared shape's key raises with a clear "component declared `active` but pipeline did not emit `active`" message.
- Edge case: pipeline output emits the *wrong* shape (e.g., `entries`/`exits`) → rejected.
- Edge case (symmetric): manifest declares `target_weights` but pipeline emits an `active`-shaped DataFrame → rejected with a "declared vs emitted shape mismatch" message naming both.

**Verification:**
- `pytest tests/unit/research/aegis_research/test_optimization_component_source.py` passes; `pytest tests/unit/research/aegis_research/test_optimization_*.py` passes.

---

- [ ] U8. **Test surface migration — contract, diagnostics, and registry tests**

**Goal:** Rewrite the canonical contract tests against target allocation; update diagnostics-shape tests to v3; update registry tests for `output_name`. This is the heart of the test migration — the contract evidence layer.

**Requirements:** R17.

**Dependencies:** U1–U7.

**Files:**
- Modify (rewrite): `tests/integration/research/aegis_research/test_portfolios.py`
- Create (test impls land here; U1 scaffolds this file): `tests/integration/research/aegis_research/test_portfolio_policy.py`
- Modify: `tests/unit/research/aegis_research/test_reports.py`
- Modify: `tests/unit/research/aegis_research/test_component_registry.py`

**Approach:**
- Remove from `test_portfolios.py`: `test_later_entries_do_not_rebalance_existing_positions` (line 305), `test_entry_budget_is_split_across_same_bar_executable_entries` (line 56), `test_single_entry_uses_explicit_entry_budget_not_implicit_full_allocation` (line 250), `test_repeated_raw_entries_are_delegated_to_vbt_order_resolution` (line 332). They lock in semantics the new contract inverts.
- Remove: `test_next_open_requires_open_prices` (line 354) and open-price guards (367-419). Close execution does not require open prices; these guards become unreachable. Keep symbol/index mismatch guards (still relevant).
- Add new tests asserting AE1 (NaN row no-rebalance), AE2 (zero row closes at close), AE4 (full liquidation under shared cash), AE5 (candidate grouping in batch), AE6 (split-gap masking + terminal liquidation before PFO via diagnostic), AE8 (diagnostics v3 shape including `terminal_liquidation=True`, `execution_timing="close"`), and a new end-to-end terminal-liquidation test (positions held into the last bar are sold at the terminal close; final cash equals final equity).
- `test_reports.py`: update diagnostics-shape assertions to v3 fields.
- `test_component_registry.py`: replace `signal_outputs == {"entries", "exits"}` assertions with `output_name ∈ {active, scores, ranks, target_weights}` (all four registered); add `entries` and `momentum` rejection tests (AE7 coverage at registry boundary).

**Patterns to follow:**
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md` — representative test naming (`test_removed_<field>_fails_as_unknown_field`, `test_portfolio_direction_is_long_only_for_v1_signal_contract`).

**Test scenarios:** (this unit *is* tests; scenarios are the AE coverage)
- AE1: NaN allocations row → no rebalance, positions persist. **Covers AE1, R4.**
- AE2: all-0.0 allocations row → positions close at the same bar's close. **Covers AE2, R4, R5.**
- AE3: `local_trend_filter` `active` output routed through policy with `target_exposure_cap=1.0` produces equal-weight allocations frame. **Covers AE3, R3.**
- AE4: full-A → full-B switch under shared cash → A sold, B bought, single rebalance. **Covers AE4, R5, R9.**
- AE5: batched run with three candidates and `vbt.ExceptLevel(SYMBOL_LEVEL)` → each candidate is its own shared-cash group, identity preserved in `pfo.allocations`. **Covers AE5, R9, R10.**
- AE6: split-gap non-executable rows counted in `diagnostics.non_executable` before PFO sees the frame; PFO does not receive split-gap rows as targets. Terminal row is rewritten to `0.0` (liquidation) before PFO. **Covers AE6, R8.**
- Terminal liquidation: a run where any positions would otherwise persist to the last bar → final cash equals final equity; final assets per symbol = 0; terminal row appears in `pfo.alloc_records` as a sell at the last close.
- AE7: component manifest with `entries`, `scores`, or `ranks` shape rejected at registration. **Covers AE7, R2, R12.**
- AE8: v3 diagnostics contains every R13 field and none of the removed legacy fields. **Covers AE8, R13.**
- Edge case: a NaN allocations row between two real-target rows behaves as documented in AE1.
- Integration: end-to-end `local_trend_filter` → `convert_to_allocations` → `apply_executable_mask` → `simulate_portfolio` → diagnostics produces a coherent `vbt.Portfolio` and v3 diagnostics payload.

**Verification:**
- `pytest tests/integration/research/aegis_research/test_portfolios.py tests/integration/research/aegis_research/test_portfolio_policy.py tests/unit/research/aegis_research/test_reports.py tests/unit/research/aegis_research/test_component_registry.py` passes.
- No test in `test_portfolios.py` references `entries`, `exits`, `entry_budget`, `valuepercent`, or `allocation_mode == "event_style_signals"`.

---

- [ ] U9. **Public docs: target allocation as the only multi-asset contract**

**Goal:** Update public-facing documentation so new authors learn target allocation first.

**Requirements:** R14, R17.

**Dependencies:** U1–U8 and U10–U12 (contract must be settled and tests must pass). Sequenced last by U-ID stability rule (U9 was originally adjacent to U8; U10–U12 were appended as the U8 split).

**Files:**
- Modify: `docs/components.md`
- Modify: `docs/vectorbt-scaffold.md`

**Approach:**
- `docs/components.md:26`: rewrite the strategy-callable section. Strategy callables emit exactly one declared allocation-native output from `{active, scores, ranks, target_weights}`. Selection convention: non-NaN cells = selected this rebalance row; NaN = excluded. Top-N is owned by the component (it chooses what to NaN out). Portfolio policy owns conversion to a validated allocations frame; the runtime hands the frame to `vbt.PFO.from_filled_allocations` and `vbt.Portfolio.from_optimizer`. Components do not own portfolios, official metrics, or arbitrary VBT kwargs.
- `docs/vectorbt-scaffold.md:81,110,114,118,199,200`: replace the `Portfolio.from_signals(valuepercent)` baseline with the PFO substrate. Document `portfolio.target_exposure_cap` (gross cap, units of portfolio value), `size_type="targetpercent"`, `pf_method="from_orders"`, `direction="longonly"` (forced), `call_seq="auto"` (frozen for v1), default `price="close"` (close-decision, close-execution), `cash_sharing=True`, `group_by={True | vbt.ExceptLevel(SYMBOL_LEVEL)}`. State `target_weights[t] = 0` closes existing positions at `t` close. Document terminal liquidation as the single forward path: any position held into the terminal bar is closed at the terminal bar's close via `allocations.iloc[-1] = 0.0`, producing a cash-realized terminal (no MTM phantom). Cite the maintainer's stance on potential close-execution lookahead.
- Cross-link to the brainstorm requirements and this plan for historical context (`docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md`, this plan file).

**Patterns to follow:**
- Tone and structure of existing `docs/vectorbt-scaffold.md` and `docs/components.md`.

**Test scenarios:**
- Test expectation: none — documentation update with no behavioral code change. Verification is editorial review.

**Verification:**
- A reader of the updated docs learns target allocation as the only multi-asset contract and does not see `entries`/`exits` or `entry_budget` presented as supported. The four allocation-native shapes and the implicit-from-non-NaN selection convention are documented.

---

- [ ] U10. **Test surface migration — config rejection tests**

**Goal:** Implement the config-validation tests for the `entry_budget` → `target_exposure_cap` rename. Asserts unknown-field rejection and the rejection cascade in lane config contracts.

**Requirements:** R11, R12.

**Dependencies:** U6.

**Files:**
- Modify: `tests/integration/research/aegis_research/test_config_contract.py`
- Modify: `tests/integration/research/aegis_research/test_lane_config_contract.py`

**Approach:**
- Add `test_removed_entry_budget_field_fails_as_unknown_field` (per the forward-first-long-only-signal-contract template).
- Update existing `portfolio.size` / `portfolio.size_type` rejection tests for the new validator shape.
- Add positive test: config with `portfolio.target_exposure_cap=0.8` validates.
- Add edge: `target_exposure_cap` out of `(0, 1]` fails.
- Add edge: config carrying both `entry_budget` and `target_exposure_cap` fails first on `entry_budget`.

**Patterns to follow:**
- `docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`.
- `docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md` (`ConfigValidationIssue(path, message)` shape).

**Test scenarios:** (this unit *is* tests; scenarios mirror U6's enumerated coverage — see U6 test scenarios)

**Verification:**
- `pytest tests/integration/research/aegis_research/test_config_contract.py tests/integration/research/aegis_research/test_lane_config_contract.py` passes.

---

- [ ] U11. **Test surface migration — fixture cascade and integration tests**

**Goal:** Update test fixtures and the integration tests that consume them. Fixture-driven cascade — these tests fail only because the fixtures change shape.

**Requirements:** R15, R17.

**Dependencies:** U5 (`local_trend_filter` converted), U6 (config rename).

**Files:**
- Modify: `tests/support/research/aegis_research/run_config_fixtures.py` (emit `target_exposure_cap`)
- Modify: `tests/support/research/aegis_research/component_fixtures.py` (emit `output_name="active"` for `local_trend_filter`-shaped fixture)
- Modify: `tests/integration/research/aegis_research/test_cli.py`
- Modify: `tests/integration/research/aegis_research/test_strategy_run.py`
- Modify: `tests/integration/research/aegis_research/test_run_playbook_sources.py`

**Approach:**
- Fixtures emit the renamed field and the new manifest shape; consumer tests pick up the new shape transparently if they were not pinning on the old field names.
- Where consumer tests assert specific manifest/config shapes, adjust the assertion (not the underlying fixture API surface).

**Patterns to follow:**
- Existing fixture conventions in `tests/support/research/aegis_research/`.

**Test scenarios:**
- Integration: `test_strategy_run.py` happy-path passes with the new fixture shape end-to-end through `local_trend_filter` → policy → PFO substrate.
- Integration: `test_cli.py` accepts a config with `target_exposure_cap` and runs end-to-end.
- Integration: `test_run_playbook_sources.py` continues to operate against the renamed config field.

**Verification:**
- `pytest tests/integration/research/aegis_research/test_cli.py tests/integration/research/aegis_research/test_strategy_run.py tests/integration/research/aegis_research/test_run_playbook_sources.py` passes.

---

- [ ] U12. **Test surface migration — optimization unit tests**

**Goal:** Update the optimization-runner-adjacent unit tests for the new substrate. These tests exercise candidate sweep, candidate store, evidence, execute-validation, and promotion against the optimization runner.

**Requirements:** R10, R17.

**Dependencies:** U7 (optimization runner rewrite).

**Files:**
- Modify: `tests/unit/research/aegis_research/test_optimization_component_source.py` (strategy output handoff)
- Modify: `tests/unit/research/aegis_research/test_optimization_candidate_store.py`
- Modify: `tests/unit/research/aegis_research/test_optimization_evidence.py`
- Modify: `tests/unit/research/aegis_research/test_optimization_execute_validation.py`
- Modify: `tests/unit/research/aegis_research/test_optimization_promotion.py`
- Modify (verify need): `tests/unit/research/aegis_research/test_optimization_failure_paths.py` — may need fixture updates if it exercises the runner's pipeline-output extraction

**Approach:**
- Replace `entries`/`exits` synthesizing helpers with allocation-output synthesizing helpers.
- Update assertions on `_coerce_pipeline_signals` → `_coerce_pipeline_output`.
- For evidence/promotion tests: update diagnostics-payload-shape assertions to v3.

**Patterns to follow:**
- Existing test helpers under `tests/unit/research/aegis_research/`.

**Test scenarios:**
- Happy path: candidate store accepts an `active`-shaped output and persists snapshot with `output_name="active"` in the registered manifest.
- Happy path: evidence/promotion ingest v3 diagnostics correctly.
- Edge case: failure-paths test still exercises the runner's error surface with the new pipeline-extraction contract.

**Verification:**
- `pytest tests/unit/research/aegis_research/test_optimization_*.py` passes.

---

## System-Wide Impact

- **Interaction graph:** the optimization runner (`research/aegis_research/optimization/runner.py`) is the only runtime caller of `simulate_portfolio[_batch]`. The component registry registers strategies that the runner consumes. The config validation layer guards the portfolio config. All three touchpoints land in this PR.
- **Error propagation:** invalid component output, bad allocations frame, unknown config field — all fail closed at the policy or validator boundary with a `ConfigValidationIssue`-style or `ValueError` with explicit messages. No silent fallback.
- **Terminal liquidation is the substrate contract.** Every position held into the terminal bar is closed at that bar's close. Final equity = final cash; no MTM phantom in downstream metrics. Empirically verified via `vbt.run_code` (2026-05-22). This is a deliberate behavior change relative to v0 (where `from_signals + exits.iloc[-1] = True + nextopen` silently dropped the terminal exit, leaving positions open) — v1 candidate rankings will differ from v0 on this dimension and that's correct: v0 was wrong, v1 matches the dominant VBT pattern and the maintainer's blessed terminal-handling.
- **State lifecycle risks:** invalid allocations (negative, sum > cap, duplicate columns, misaligned to `close`) fail at the policy boundary before reaching PFO. No partial-write risk inside the substrate. Diagnostics payload is whole-or-nothing per run.
- **API surface parity:** the runner's `simulate_portfolio` / `simulate_portfolio_batch` signature changes. The optimization runner is the only in-tree caller; no external consumers. CLI, run_splits, strategy_runs do not directly call this surface (verified during planning).
- **Integration coverage:** the end-to-end scenario `local_trend_filter` → registry → optimization runner → policy → masking → PFO → from_optimizer → diagnostics is covered by U8's integration tests in `test_portfolios.py` and U11's in `test_strategy_run.py`.
- **Unchanged invariants:** `direction="longonly"` remains a frozen invariant for v1. `cash_sharing=True` and `call_seq="auto"` remain frozen. The `SYMBOL_LEVEL` constant is unchanged and remains the canonical column level name for candidate-grouping. `PortfolioSimulationResult` dataclass is unchanged. `portfolio_record_counts` is unchanged. `expand_market_frame_to_candidate_columns` is unchanged.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| VBT defaults `nonzero_only=True` / `unique_only=True` silently drop closing or unchanged rows | Pass `nonzero_only=False, unique_only=False` explicitly to `from_filled_allocations`; AE2 test asserts close-on-zero behavior; new test asserts consecutive identical targets both register as rebalance rows. |
| pandas 2.2 alphabetical column reorder corrupts target-percent column ↔ symbol mapping | Reindex every component output to `close.columns` and assert `.equals` inside `portfolio_policy.policy`; named in U1 test scenarios. |
| `from_optimizer` direction inference flips to `"both"` if a tiny negative slips through validation rounding | Pass `direction="longonly"` explicitly; policy rejects any negative target_weights before they reach PFO. |
| Close-decision close-execution exposes same-bar lookahead for components whose signal uses the close price | Substrate is consistent with the dominant VBT cross-sectional pattern and the maintainer's stated position. If a future research workflow requires strict no-lookahead semantics, that's a separate substrate brainstorm. For v1: documented in U9; researchers are aware. |
| Terminal liquidation changes v0 → v1 candidate ranking (v0 silently held positions at terminal; v1 closes them) | Intentional. v0's behavior was a silent bug (`exits.iloc[-1]=True + nextopen` is a no-op). v1 matches the dominant VBT pattern. Document the behavioral change loudly in U9 so researchers comparing v0 baselines understand the delta. |
| Diagnostics consumers (reports, evidence stores) depend on v2 schema | Schema version bump signals the change; downstream `test_reports.py` updated in U8; any external consumer breaks loudly via schema_version mismatch (intentional). |
| Optimization performance plan (#002) U2/U5 currently hedges "concurrent landing" | This plan becomes #002's prerequisite. Documentation-only edit to #002 deferred to follow-up; U2/U5 in #002 will read the new substrate cleanly once this PR lands. |
| Order rejection (NoCash) silently under-fills target-percent rebalances at gross cap | New `order_rejections` diagnostic block surfaces counts (per solutions library finding); U3 includes a test that forces a NoCash and asserts the count appears. |

---

## Documentation / Operational Notes

- **Migration PR scope**: single PR for U1–U12. No interim states; the runtime must be coherent at every commit boundary inside the PR (U-IDs are commit-shaped).
- **Recommended commit ordering**: U1 + U6 (foundations, no deps) → U4 (depends on U6) → U5 (depends on U4) → U2 + U7 + U3 land together as a single substrate-switch commit (otherwise the optimization runner is calling the new `simulate_portfolio` signature against the old entries/exits path, leaving tests temporarily broken) → U8 (contract tests) → U10 + U11 + U12 in parallel (independent test surfaces) → U9 (docs, depends on everything settling). This is a recommendation, not a U-ID stability constraint.
- **Schema version bump signals downstream**: `portfolio_diagnostics.v3` triggers downstream report consumers to update their expectations. Treat this as the breakage signal.
- **Plan #002 (`docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md`) sequencing**: this plan lands first. After landing, file a small follow-up to remove the "concurrent landing" hedge wording in #002's U2 and U5.
- **No new feature flags or rollout mechanics**: forward-first migration; no opt-in legacy mode.
- **Diagnostic field reference for reports/evidence**: report-side consumers (`tests/unit/research/aegis_research/test_reports.py` consumers) read from `_portfolio_diagnostics`. Adjust their assertions in U8.

---

## Sources & References

- **Origin document:** [`docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md`](docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md)
- **Related plans:**
  - [`docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md`](docs/plans/2026-05-22-002-feat-vbt-native-optimization-performance-upgrade-plan.md) — downstream consumer; this plan is its prerequisite.
  - [`docs/plans/2026-05-18-001-feat-portfolio-simulation-contract-plan.md`](docs/plans/2026-05-18-001-feat-portfolio-simulation-contract-plan.md) — predecessor; the v1 portfolio contract that deferred PFO. This plan activates the deferral.
- **Related brainstorms:**
  - [`docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md`](docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md) — the brainstorm that named PFO as the future substrate.
- **Related issues:** #35 (this plan's body), #4 (the original portfolio simulation contract).
- **Solutions library:**
  - [`docs/solutions/best-practices/vectorbt-weights-from-signals-vs-orders-2026-05-17.md`](docs/solutions/best-practices/vectorbt-weights-from-signals-vs-orders-2026-05-17.md)
  - [`docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md`](docs/solutions/best-practices/forward-first-long-only-signal-contract-2026-05-18.md)
  - [`docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md`](docs/solutions/architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md)
  - [`docs/solutions/best-practices/vectorbt-execution-timing-nextopen-2026-05-17.md`](docs/solutions/best-practices/vectorbt-execution-timing-nextopen-2026-05-17.md)
  - [`docs/solutions/best-practices/vectorbt-close-optimizer-positions-at-end-2026-05-17.md`](docs/solutions/best-practices/vectorbt-close-optimizer-positions-at-end-2026-05-17.md)
  - [`docs/solutions/best-practices/vectorbt-targetpercent-nocash-rejections-2026-05-17.md`](docs/solutions/best-practices/vectorbt-targetpercent-nocash-rejections-2026-05-17.md)
  - [`docs/solutions/logic-errors/vectorbt-allocation-column-alignment-2026-05-17.md`](docs/solutions/logic-errors/vectorbt-allocation-column-alignment-2026-05-17.md)
  - [`docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`](docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md)
- **VBT PRO source (read-only references):**
  - `vectorbtpro/portfolio/pfopt/base.py:2755` (`from_filled_allocations`)
  - `vectorbtpro/portfolio/pfopt/nb.py:28` (`get_alloc_points_nb`)
  - `vectorbtpro/portfolio/base.py:6011` (`from_optimizer`)
  - `vectorbtpro/portfolio/preparing.py:1095-1141` (`price="nextopen"` lowering)
  - `vectorbtpro/portfolio/enums.py:212` (`CallSeqType.Auto`)
  - `vectorbtpro/base/indexes.py:40` (`ExceptLevel`)
