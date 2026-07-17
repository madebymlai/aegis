# Exposure Validation is one kernel-owned gate

Status: accepted (as built, aegis-rd-spwu). Applies ADR-0006's recipe to the last
remaining duplicate on the research↔execution seam.

The fail-closed gross/net/sign gate was implemented twice — `aegis_runtime/bundle.py`
gated the live **Execution Bundle**, and research's `exposure_validation/validation.py`
gated every simulation (a superset adding per-**Candidate** gating) — with the shared
knowledge (tolerance `1e-9`, the **Direction** vocabulary, both cap inequalities, error
wording) kept identical only by discipline. A drift would have meant live weights passing
a gate research never validated. We collapse to one kernel module,
`aegis_runtime/exposure_validation.py`, and delete the research package:

- **`ExposureLimits`** is the validated caps value object (gross cap, net cap defaulting
  to gross, Direction) — construction is the proof the triple is legal. It names the
  **Exposure Limits** term aegis-rd's glossary already defined. `LockedExecutionPlan`
  and research's `PortfolioConfig` expose `.exposure_limits`, so both call sites read
  `validate_exposure(frame, <holder>.exposure_limits)`.
- **Grouping crosses the seam as opaque labels.** `validate_exposure(..., group_by=,
  describe_group=)` gates each distinct label's columns independently, vectorized in one
  groupby pass; `describe_group` lets the caller phrase the offender in its own
  vocabulary (research passes `candidate {id!r}`). The kernel never learns what a
  Candidate or a `symbol` level is — research derives labels via
  `columns.droplevel(SYMBOL_LEVEL)` at its one call site (`portfolios.py`).
- **The research plain-columns path is deleted, not ported.** In production research only
  ever gated candidate-expanded frames (`simulate_single_book` is a test-support wrapper
  that expands first); the single-book branch existed only for its own tests.
- **The gate math test surface moves kernel-side** (`aegis-runtime/tests/
  test_exposure_validation.py`); research keeps one wiring test through
  `simulate_portfolio_batch` (label derivation + Candidate phrasing).

## Considered options

- **Share only the semantics (constants + sign guard), keep research's grouped math**:
  rejected — the cap inequalities would still live in two homes, needing a parity test to
  hold them together; parameterizing the reduction dissolves the second implementation
  entirely.
- **Research loops per Candidate over a scalar kernel gate**: rejected — a Python loop
  over thousands of Candidates in the sweep hot path, and the kernel's errors cannot name
  the offender without catch-and-rewrap.
- **Kernel learns the Candidate/`SYMBOL_LEVEL` MultiIndex shape**: rejected — the
  research apparatus must not cross into execution (Context Map; same firewall ADR-0006
  respected).

## Amendment (2026-07-09): Trader reuses the kernel's net policy

Research and an Execution Bundle remain the two full gross/net/Direction validation
scopes. Trader has a different gross operation: it proportionally clamps both the netted
target and the planned post-band book to its Commingled Book `gross_cap`. Because that clamp is
authoritative, a second gross comparison would be unreachable defensive policy.

Trader delegates only its reachable explicit net cap to
`validate_net_exposure(frame, net_cap)`. That operation lives beside the full gate and
reuses its comparison, `1e-9` tolerance, and `NetExposureBreach`; Trader owns projection,
gross clamping, and per-name remediation. `BookConfig` constructs one validated
`ExposureLimits` value from its real gross cap and optional net cap; a book with no explicit
net cap invokes no net operation.

The Trader limits govern the Commingled Book after allocation and netting. They are not
provenance projections of the standalone Sleeve limits carried by Execution Bundles, so no
Book-to-Sleeve cap comparison is made at startup.

The kernel leaves allocation values unchanged. In research, `NaN` remains the simulator's
sparse "no new allocation" instruction, and grouped reductions use `dropna=False` so every
supplied group remains part of the gate.

## Amendment (2026-07-10): the research call site moved behind Window Evaluation

RD ADR-0026 made portfolio simulation internal to Window Evaluation. Research's one
mandated wiring test through `simulate_portfolio_batch` (label derivation + Candidate
phrasing) is unchanged in substance but now crosses Window Evaluation's internal
simulation seam; the research call site is `optimization/window_evaluation/_simulation.py`
rather than `portfolios.py`. The kernel-side surface and test home are untouched.
