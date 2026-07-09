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

## Amendment (2026-07-09): Trader's realized book is the third validation scope

The same kernel interface now gates Trader's realized post-band book. `BookConfig`
projects its optional book caps into one `ExposureLimits` value. The Rebalancer gates
both its planned post-band projection and the executable projection reconstructed after
sizing, rounding, and availability filtering; it no longer owns a second gross/net
comparison, tolerance, or error vocabulary. Trader still owns the distinct work that
belongs to its actor: projection, the down-only `max_book_gross` clamp, per-name
remediation, and the decision to halt when the final book remains non-compliant.

Exposure Validation therefore serves three scopes with one policy:

- research gates Candidate-expanded frames before simulation;
- an Execution Bundle gates one Sleeve's signed allocation;
- Trader gates the planned and executable realized Commingled Book projections.

The kernel accepts explicit all-NaN no-rebalance groups for research, but Trader's
one-row realized book selects the strict input policy and must be entirely finite.
Missing group labels and invalid cap values fail at the kernel boundary, so no Pandas
reduction or IEEE NaN comparison can silently remove exposure from the gate.
