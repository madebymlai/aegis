# Portfolio diagnostics are a test oracle, not Evidence

`research/aegis_research/portfolios.py` emits a schema-versioned `portfolio_diagnostics.v4`
dict that looks exactly like an **Evidence** artifact — `schema_version`, a `vbt_settings`
contract echo, a structured `financing_carry` block (kqg.9), grouping, rebalance rows,
realized-vs-requested allocations. But it is never recorded into the **Run**'s Evidence
ledger. The `EvidenceSection` enum has only `preflight`/`execution`/`candidates`; the one
production caller (`optimization/runner.py`) invokes `simulate_portfolio_batch(...,
compute_diagnostics=False)` and discards the dict; and the pfo-contract plan
(`2026-05-22-003`) authored these fields *knowing* nothing reads them ("no current in-tree
consumer reads… the optimization runner discards `result.diagnostics`"). The dict's only
consumers are the 29 tests in `tests/integration/.../test_portfolios.py`.

We decided the diagnostics are **test instrumentation, not Evidence**, and we remove the
Evidence costume rather than wire it in. The `schema_version`, the `compute_diagnostics`
flag, and the `PortfolioSimulationResult.diagnostics` field are deleted; the result collapses
to a bare `vbt.Portfolio` (the metrics path already reads `pf` directly). The describe job
(`_portfolio_diagnostics`, `_financing_carry_diagnostics`, `_allocations_diagnostics`,
`_realized_weights_at_fill`) and its serialization tail (`_serialize_sparse_frame`,
`_column_label`, `_scalar`) are deleted, not relocated — they existed only to produce the
shape that shape-asserting tests check, which is testing test-code. The tests are triaged:
assertions that pinned only the dict's shape (schema_version, the `vbt_settings`/`contract`
config echoes, dict-key-set checks, the `financing_carry` rate echo) are deleted; assertions
that pinned a real production fact are ported to read their source directly — rebalance dates
from `pfo.alloc_records`, grouping from `pf.wrapper.grouper`, non-executable counts from
`portfolio_policy`'s `apply_executable_mask_and_terminal_liquidation` return, record counts
from native `pf.orders/trades/exit_trades.count()`, realized-at-fill from `pf.get_allocations`.

**Carry auditability does not depend on this dict.** A Run's `resolved_config.v1` artifact
(defaults applied) is written to the run folder and hash-pinned twice — `resolved_config_hash`
in config Evidence and the Manifest artifact hash — and it already carries
`short_borrow_rate`, `short_rebate_rate`, and the `freq`/`year_freq` that derive
`periods_per_year`. That is the stronger record than a non-persisted diagnostics block. Under
the system's audit model (CONTEXT.md **Evidence**: persist the claim, persist what reproduces
it; ADR-0009: the auditor re-runs the **Lock** on the same machine), per-bar carry-as-charged
has exactly the same status as per-bar fees, slippage, and fills — none persisted, all
auditable by reproduction. Singling out carry for bespoke persistence would be ad-hoc Evidence
with no principle that stops at one cost. kqg.9's "carry transparency" was developer-facing
verification that the mechanism worked during the epic — fulfilled instrumentation, the same
pattern as the carry demo deleted in `ae063ab`.

## Considered options

- **(a) Wire the diagnostics into the Evidence ledger** (treat it as the latent contract it
  resembles): rejected. It has no production home. The only production simulation is the hot
  sweep path, which candidate 1 froze at `compute_diagnostics=False` to keep diagnostics cost
  off the per-split, per-candidate path; the single-portfolio path has zero production callers;
  and no representative-candidate re-simulation stage exists in `publishing`. Branch (a) would
  require inventing a new production stage whose only purpose is to feed an artifact nobody
  reads — building a consumer to justify a producer.
- **(b) Honest test oracle** (chosen): the diagnostics exist so integration tests can observe
  VBT execution facts. Relabel by deletion — drop the schema_version costume, collapse the
  result, triage the tests onto their real sources. The misleading element was never that the
  observations exist; it was that they wore a `schema_version`, which in this codebase means
  "persisted, hash-pinned Evidence." Removing it protects that vocabulary.
- **(c) A small persisted carry core + a rich test-only layer**: rejected. The persisted core
  would duplicate `resolved_config.v1`, which already pins every carry input; the only field
  not in the resolved config is the mechanism string, which the Manifest already pins via git
  commit + package versions. Zero added auditability for a new persistence rule.

**Fidelity-gate placement (sub-decision).** `assert_requested_realized_fidelity` is a
fail-closed check (kqg.7), but rode along inside the test-only diagnostics path, so it never
fired in production. It guards the `cash_sharing` + multi-asset-leverage mis-fill that silently
turns a market-neutral long/short book net-long (ADR-0007). VBT confirms `leverage_mode="eager"`
is only a *partial* fix: it applies leverage capacity per-order (closing the documented
under-fill) but cannot conjure cash to close a losing short — the residual `NoCash` failure is
input- and path-dependent, not VBT-version-determined, so a fixed-fixture CI test is a sample,
not a proof. We therefore **split the gate**: a cheap fail-closed invariant runs on the
production hot path reading the native `pf.logs.res_status_info_no_cash` field (an O(records)
reduction — not the `records_readable` build, not `get_allocations` — so candidate 1's freeze
is not re-violated), while the rich requested≈realized frame comparison stays test-side, renamed
a VBT-contract regression guard and labeled a sample. The same split replaces
`_order_rejection_counts`' string-matching over `records_readable` with the native `res_status_*`
fields, deleting the hand-maintained `ORDER_REJECTION_STATUSES` tuple.

## Amendment (2026-06-09): the production guard is an exact NoCash tripwire, not a tolerance

The fidelity-gate split above assumed the production guard would carry a tolerance (it must
distinguish a benign `NoCash` — VBT re-executing an unchanged target when free cash is zero —
from a genuine under-fill). aegis-rd-ce4.1 implemented exactly that: a
`_NOCASH_ALLOC_MISMATCH_TOLERANCE` classifier comparing the requested target against the held
allocation. That tolerance is being removed.

The benign `NoCash` class only exists because free cash can be pinned at zero against the
engine's `leverage=gross_cap` ceiling. The ADR-0007 amendment (2026-06-09) removes that
ceiling — the **Allocation Policy** gate becomes the sole enforcer of `gross_cap` and the
engine runs with surplus buying power (`leverage = k × gross_cap`). With no zero-buying-power
states, **every `NoCash` rejection is a bug**, so the guard collapses to an exact tripwire
(`if any(NoCash): raise`) with no tolerance, no `req_size`/`st0_*` reconstruction, and no
benign-vs-genuine classifier. The categorical improvement: the old threshold *graded
corruption* (a judgment with no right answer); the headroom *sizes a resource* (correct value
is just "enough"), and the tripwire stays exact at zero forever. If it ever fires, the response
is a capacity bump, not a recalibration. Tracked as a `discovered-from` follow-up to
aegis-rd-ce4.1.

## Consequences

- `PortfolioSimulationResult` is removed; `simulate_portfolio_batch` returns `vbt.Portfolio`
  directly. The single-portfolio `simulate_portfolio` (zero production callers) is deleted in
  favor of batch-of-1, gated on a one-shot test proving `ExceptLevel`-of-one-candidate is
  numerically identical to `group_by=True` over plain symbols; a test-support
  `simulate_single_book` wrapper keeps the carry/mechanics tests readable.
- `financing_carry` (`short_masked_cash_dividends`) stays in `portfolios.py`: one pure
  function, one caller, no native VBT shortcut to hide behind. It does not earn its own module.
- `ReportConfig` is the sole owner of the annualization calendar; `periods_per_year` stays a
  required threaded parameter and the `DEFAULT_PERIODS_PER_YEAR = 252` fallback is deleted (it
  was a second calendar source, live only on the now-deleted single path). Coordinates with the
  Metric-layer deepening (candidate 2): metric annualization reads the same field, per ADR-0008's
  "carry and the performance metrics share one calendar."
- The 636-loc, five-job file reduces to one job — VBT orchestration — plus the pure carry
  function, the `portfolio_policy` gate call, and the cheap NoCash production invariant.
- No CONTEXT.md change: no domain term is minted. The decision *protects* the existing
  **Evidence** / **Canonical Form** vocabulary by ensuring `schema_version` continues to mean
  "persisted Evidence artifact" and nothing else.
- Touches the shared `runner.py` → `simulate_portfolio_batch` → metrics surface; merge order
  must coordinate with sibling candidates 1 (validity), 2 (metrics), and 3 (param codec).

## Amendment (2026-06-10): a run-level non-executable-row scalar in execution Evidence is in-bounds

This ADR (line 26) classified the **non-executable count** — read directly from the masking
step's return — as a **test oracle** fact, ported to read its source rather than persisted.
The `aegis-rd-oh4` epic then deliberately routes a single run-level `non_executable_rows`
integer into the Run's **execution** Evidence (`candidate_evidence.result_evidence` →
`optimization_result.v3`, recorded under `EvidenceSection.EXECUTION`). On its face that
overturns this ADR. It does not: the **facts on the ground changed**, and the new placement
*honors* this ADR's principle rather than weakening it.

**What changed.** When this ADR was written, the non-executable count was a byproduct of a
**test-only** path. Masking lived in `portfolio_policy`; the runner discarded the diagnostics
dict; and the mask was provably inert in production because the runner passed the *window's
own* index as the market index, so seams could never be detected. The count had no production
home, so it was correctly a test fact. oh4 **moved masking into the production simulation
boundary** (oh4.2) and **armed it with the full market calendar** (oh4.3 — a reproduced bug
fix: purged-split held-out windows were filling across purge seams). The count is now produced
*on the production path*, where it records the structural execution cost of non-contiguous
(purged/embargoed) split windows — zero for contiguous methods (an invariant), positive by
design under purged modes. Its classification changed because its **production status**
changed, not because this ADR's rule was loosened.

**Why it is not the artifact this ADR rejected.** This ADR killed a *standalone*
`portfolio_diagnostics.v4` dict that (1) wore its **own** `schema_version`, (2) was recorded
into **no** Evidence section (the runner discarded it), (3) carried a structurally-fake
per-symbol breakdown, and (4) had **zero** production consumers. `non_executable_rows` is none
of these. It is a single integer; it carries **no** `schema_version` of its own (it rides
under `OPTIMIZATION_RESULT_SCHEMA_VERSION`, an artifact that genuinely *is* persisted and
read); it is recorded into the real `EXECUTION` section; and it has real consumers — the oh4.4
run-report line (neutral under purged methods, WARNING-prefixed under contiguous methods where
a non-zero value flags an upstream invariant breach) and the persisted `strategy_run.json`
artifact, both of which read it back **from the recorded Evidence ledger**
(`run_evidence.optimization()["execution"]`), not from a side channel. Option (a)'s specific
objection — "inventing a new production stage whose only purpose is to feed an artifact nobody
reads" — therefore does not apply: no new stage was invented, and the artifact is read.

**Parity with already-accepted siblings.** The same `optimization_result.v3` block already
persists `total`, `excluded_invalid`, and `excluded_degenerate` — run-level accounting
integers that are *also* deterministically reproducible from the pinned config and that the
run report already consumes (the researched-ratio line). Those were accepted as Evidence.
`non_executable_rows` is categorically identical: a run-level integer recording what the sweep
did. No principled line admits the exclusion counts onto the result deliverable but evicts
this one.

**The honest counter, and its resolution.** Read literally, this ADR's reproducibility test
(lines 29-40) — "persist only what reproduction cannot recover" — would evict
`non_executable_rows`, since re-running the Lock recomputes it exactly (it is a pure function
of split geometry and the pinned calendar). But that same literal reading would also evict the
exclusion counts above, which are persisted and accepted. The operative, as-practiced
principle is therefore narrower than the literal test: **do not mint a standalone
`schema_version` artifact for a non-persisted, unread observation.** Run-level accounting
integers that ride on the genuinely-persisted **result deliverable** and have a real reader
are in-bounds. `non_executable_rows` satisfies that; the rejected diagnostics dict did not. The
`schema_version`-means-persisted-Evidence vocabulary this ADR protects is **upheld, not
diluted** — the count never wears the costume on its own; it lives inside an artifact that
genuinely earns it.

**Verdict:** keep `non_executable_rows` in execution Evidence. No code change. This amendment
is the paper trail, so the placement is not re-opened as a review finding.
