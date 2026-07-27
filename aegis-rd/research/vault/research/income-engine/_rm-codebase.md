---
title: "Convergent Engine - codebase verification (RM-4, RM-7, RM-9)"
date: 2026-07-25
tags:
  - integrity
  - income-engine
---

# Codebase verification - RM-4, RM-7, RM-9

Verifying three P0 docket items against the repository as it stands, not against the corpus's prior
descriptions of itself. Method: read the code, the commits, the run outputs, and the issue records
directly; report what exists and what does not.

## Summary verdicts

- **RM-9.** Not a horizon effect and not a two-code-path inconsistency: `downside_correlation` is the
  only function that ever computes this guard, it has no horizon parameter, and it fully reproduces
  +0.2724. +0.253 has no call path anywhere in the repository - it is asserted in a commit message and
  in article prose, and it is already leaking into a live experiment's keep/kill gate uncorrected.
- **RM-4.** The baseline is confirmed trend-alone, in code, with no Target or Expansion tier in either
  term. Segment-conditioned reporting is not computable today: the codebase has no episode-level,
  duration-based drawdown classifier anywhere, so nothing can distinguish "fast spike" from "protracted
  drawdown" days for conditioning purposes.
- **RM-7.** The role-redundant discriminator (responder scaled to the convergent candidate's risk budget,
  compared against responder at its own weight) does not exist anywhere in the codebase. `delta_theta`
  already nets out the only responder-only baseline that is implemented.

## RM-9 - the two downside-correlation figures

**Verdict: neither a horizon effect nor a pipeline inconsistency. One figure (+0.2724) has a complete,
reproducible call path; the other (+0.253) has none in the repository. Quote +0.2724, do not quote
+0.253 until code exists that reproduces it.**

### The +0.2724 call path, in full

`downside_correlation` is defined once, at `aegis-rd/research/aegis_research/metrics/custom/convergent.py:421`:

```python
def downside_correlation(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    quantile: float = _DOWNSIDE_QUANTILE,   # 0.10
) -> float:
```

It masks `trend_daily` to its worst 10% of **individual days** (`np.quantile(trend_daily, 0.10)`) and
returns `np.corrcoef` of the two streams on that mask. It has **no horizon, window, or band
parameter** - it is a same-day, magnitude-quantile-conditioned correlation on raw daily returns, full
stop. The "2 to 6 month band" language belongs to a different part of the module (`_left_tail_budget`,
`_HORIZON_BAND`, imported from `convexity.py`) that reports tail loss and L-skew on overlapping
multi-month windows - it is never passed to or used by `downside_correlation`.

It is called from exactly one place, `evaluate_allocator_contribution` (convergent.py:608-667), at line
665: `downside_correlation(convergent_daily, trend_daily)` - no quantile override, so `quantile=0.10`.
That function also computes `delta_theta` via `composite_allocator_utility` in the same call.

The two input arrays come from `aegis-rd/scripts/floor_evaluation.py`'s `load_locked_strategy_returns`,
which reproduces a **locked** Run Config through `build_development_paths` (the same code path a normal
Run uses) and returns one net daily return series with no aggregation. Per `bd show aegis-rd-n77e` and
commit `bf8ac1ee` ("feat(rd): load a locked config as a return series, and run the floor pair",
2026-07-25 01:46:16), the two locked configs are `atalanta/trend_floor.yaml` and
`demeter/carry_floor.yaml`, both re-locked earlier the same session, aligned to **1,889 common trading
days, 2019-01-02 to 2026-06-30**. `bf8ac1ee`'s own commit message states the result verbatim: "delta_theta
-0.014055, downside correlation +0.2724, intervals at 21/63/126d all spanning zero, earns_its_seat
False" - matching `bd show aegis-rd-n77e`'s NOTES and the "Measured 2026-07-25" callout in
`the-premium-is-rent-on-a-balance-sheet.md` exactly, including the trailing digits. Parameters used:
`convergent_weight=0.4`, `rho=3.0`, `book_vol_annual=0.10` (passed explicitly - the module's own
`DEFAULT_BOOK_VOL` constant reads `0.09` in the current file, matching `book.toml`, so the run's 0.10
was a deliberate override, not the default falling through).

There is no script or test in the repository that ties `load_locked_strategy_returns` and
`evaluate_allocator_contribution` together programmatically - the loader's own docstring says it exists
so "a run, a notebook, and a CLI all reach the same answer through it," and the one CLI that used to do
this (`scripts/floor_gate.py`) was deleted at commit `77565936`, before the loader existed. So the
+0.2724 measurement was produced by an interactive session calling both functions directly, not by a
committed script - but every input to that call (the two configs, their locks, the parameters, the
resulting figures) is independently verifiable from the commit message, the config files' own lock
headers, and the `bd` issue, and the function itself is deterministic on its two arguments. This is
fully reproducible in the sense that matters: anyone with the two locked configs and the same call
gets the same number.

### The +0.253 call path: does not exist

+0.253 appears in exactly two places in the entire repository: commit `03ece3b7`'s commit message
("The guard's +0.253 is real, and the caveat this session attached to it is withdrawn") and the
hypothesis-list entry that same commit edited in
`aegis-rd/research/vault/research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md` ("The
guard's +0.253 is real"). Grepped the full repository for the literal `0.253` - the only other hits are
unrelated (a profiling timing figure, unrelated composite scores in an `aegis` book run diary).

Commit `03ece3b7` ("feat(rd): report the sleeve's smoothing profile, and close the caveat it carried",
2026-07-25 03:27:08, 1h41m after `bf8ac1ee`) adds exactly one new function to convergent.py:
`_convergent_smoothing_index`, the Getmansky-Lo-Makarov smoothing index xi, estimated via a
Lo-MacKinlay variance ratio over a **deliberately one-month (21-day)** aggregation horizon
(`_SMOOTHING_HORIZON = 21`, convergent.py:130). This is a **single-stream** statistic - it takes one
`stream: np.ndarray` and returns one float - not a correlation, not a paired statistic at all. Its
reported value for both live poles is **xi = 1.0000** (the no-smoothing ceiling), not 0.253, and it is
measured in a different unit entirely (a variance ratio, bounded at 1, versus a correlation coefficient
bounded in [-1, 1]).

The commit message additionally reports, in prose only, "first-order autocorrelation is NEGATIVE (-0.104
convergent, -0.024 trend)... Sharpe inflation is 1.0000, and the lagged downside correlations alternate
in sign (-0.125, +0.159, -0.096) rather than decaying positively." **No function anywhere in the
repository computes a lagged or shifted downside correlation.** `downside_correlation` has never taken a
lag parameter (checked its full git history - the signature has always been
`(convergent_daily, trend_daily, *, quantile)`). No script, test, or config in the tree contains a
lagged-correlation implementation, and no `_prototyping/` probe matches. The autocorrelation figures and
the three lagged-correlation values quoted in the commit message are not backed by any code path this
session could find - they read as results of an ad hoc, uncommitted computation (a REPL or notebook
session), asserted in the commit message but never captured as reusable code, exactly the failure mode
this same commit's own docstring warns against for smoothing generally ("reported every run rather than
concluded once... because it is a property of the data feed").

### Why this is not the horizon effect D8 speculates

`_plan.md`'s D8 callout guesses the two figures are "plausibly the same guard over different windows,
since that commit deliberately uses a one-month horizon rather than the 2 to 6 month band the shape
reports use." This does not survive contact with the code for two independent reasons:

1. `downside_correlation` - the only function that has ever computed this guard - has no horizon or
   window parameter of any kind. It cannot be run at "a one-month horizon" or "a 2-6 month band"; those
   phrases describe a different metric (`_left_tail_budget`) that this guard does not use.
2. The one-month horizon that commit `03ece3b7` actually introduces belongs to `_convergent_smoothing_index`,
   a same-session addition that estimates a smoothing ratio, not a correlation, and whose own reported
   figure (1.0000) is not 0.253 either.

Since `downside_correlation` is a pure, deterministic function of its two input arrays and a fixed
quantile, an identical call on the identical 1,889-day aligned pair **must** return +0.2724, not +0.253.
The 0.0194 gap (about 7% relative) is too large to be a rounding or floating-point artifact. The only way
to get a different number from the same function is a different data slice - a different sample window,
a different pair of locked runs, a different quantile, or a subset of the series - and nothing in the
repository shows what that different call was.

### It is not a settled question that prior passes resolved, and it is now live in new work

Two earlier integrity passes in this same folder already found and declined to close this gap:
`_integrity_pass3.md` ("Docket item 6... the flag is accurate... the reconciliation itself was not
attempted, per instruction") and `_integrity_rerun.md` ("The +0.2724 versus +0.253 discrepancy was not
resolved, only flagged. I did not trace the exact computation paths"). Neither pass reports having read
`downside_correlation`'s source or `03ece3b7`'s actual diff; both reason from the commit message alone.

More importantly, the gap is no longer inert. An **uncommitted** run diary,
`aegis-rd/research/vault/runs/demeter/2026-07-25.md` (part of a later session's work the same day,
auditing a currency-hedged replacement for the convergent sleeve), states a pre-registered keep/kill
gate for a new candidate as: "KEEP if... the downside correlation to trend falls below **the incumbent's
+0.253**." The unreconciled commit-message figure is now the operative benchmark for a live experiment,
not just a number sitting in old planning documents.

### Disposition

Neither "genuine horizon effect" nor "pipeline inconsistency" (two code paths computing one nominal
quantity differently) is what this is, because there is only one code path (`downside_correlation`,
called once, from `evaluate_allocator_contribution`) and it produces +0.2724. +0.253 is an unverifiable
assertion with no call path - closer to "not currently reproducible" than to "a different statistic
sharing a name," since nothing shows what statistic it actually is. The paper should carry +0.2724 with
its full provenance (loader, locks, 1,889-day window, `evaluate_allocator_contribution` defaults) and
should not carry +0.253 in any form - including as a benchmark for future work - until someone writes and
commits the code that reproduces it.

## RM-4 - is the segment-conditioned reading computable, and what the baseline contains

**Verdict: the baseline is confirmed trend-alone with no Target or Expansion tier in either term. The
segment-conditioned reading is not computable with what exists today - the specific missing piece is an
episode-level, duration-based drawdown classifier, which nothing in the codebase implements.**

### What the baseline actually contains

`composite_allocator_utility` (convergent.py:364-418) computes:

```python
theta_book = composite_book_utility(convergent_daily, trend_daily, ...)   # the blend
trend_ref = _blended_book(trend_daily, trend_daily, convergent_weight=0.0, book_vol_annual=book_vol_annual)
theta_trend = _convergent_income_utility(trend_ref, rho)
return theta_book - theta_trend
```

`_blended_book(convergent_daily, trend_daily, *, convergent_weight, book_vol_annual)` returns
`(1 - convergent_weight) * trend_leg + convergent_weight * convergent_leg`. Passing
`convergent_weight=0.0` (as the baseline call does, on `trend_daily` in both argument slots) collapses
this to `trend_leg` alone, scaled to `book_vol_annual`. So the baseline term is, exactly as D8 states,
**Θ̂(trend alone)** - not a no-op self-comparison, not a partial blend, a single-leg trend-only book at
the mandate's volatility.

Both `trend_daily` and `convergent_daily` are loaded via the same mechanism (`load_locked_strategy_returns`
in `floor_evaluation.py`) from `atalanta/trend_floor.yaml` and `demeter/carry_floor.yaml` respectively -
single-candidate locked configs, each producing one net daily return stream from one strategy sleeve.
Grepped both config files directly for `Target` and `Expansion`: **no match in either file.** There is no
third return stream, no tier weighting, and no reference to the Target or Expansion tier anywhere in the
computation that produces ΔΘ̂ = -0.014055. This confirms `_synthesis.md` §3.5(c)(3)'s own claim verbatim
("The Target appears in neither term") from the code side, independent of that document's own reasoning.

### Is segment-conditioning computable today

`_synthesis.md` §3.5(a) requires reporting placement statistics **conditioned on the responder's
protracted-drawdown windows specifically**, distinguishing them from the fast spikes ① §4.2 assigns to
the Target tier, and reporting the fast-window loss "separately and as a cost... not netted into the
same number." That is a duration/episode classification of the trend sleeve's drawdowns (fast, days-scale
vs. protracted, monthly-or-slower), not a magnitude threshold on daily returns.

Checked what the codebase actually has to condition on:

- `downside_correlation`'s only conditioning mechanism is `np.quantile(trend_daily, 0.10)` - a magnitude
  cutoff on **individual days'** returns. A day that is part of a one-day gap and a day that is part of a
  six-month grinding bear are treated identically if both happen to fall in trend's worst 10% of single
  daily returns. This cannot distinguish fast from protracted, because it never looks at what episode a
  day belongs to or how long that episode has been running.
- `EquityCurve.drawdown_curve()` (`metrics/custom/support/equity_curve.py:71`) computes a continuous
  per-day drawdown-from-peak level (`value / value.cummax() - 1`). This is a magnitude time series, not
  an episode table - it has no start/trough/end markers and no duration field, so nothing downstream can
  ask "how long has this drawdown been running" from it directly.
- Grepped `aegis_research`'s metrics and optimization modules for `protracted`, `fast_segment`,
  `drawdown_segment`, `regime`, `market_state`: the only hits are unrelated (`ranking.py`'s module
  docstring says "regime-balanced Observation Block ranking" but that concerns balancing training folds
  across time periods for candidate selection, not classifying drawdown episodes by duration; `convexity.py`
  has a "bear-regime beta" - a benchmark-below-its-average-level beta, again a magnitude/level condition,
  not a duration classification).
- Grepped the whole repository for `.drawdowns`, `vbt.Drawdowns`, `get_drawdowns` (the vectorbtpro
  primitives that would give episode-level Start/Valley/End/Duration records): zero matches anywhere,
  including in `aegis-trader`. The underlying simulation library this codebase runs on may well expose
  drawdown-episode analytics as a general capability, but nothing in this codebase currently calls it for
  any purpose, so it is not "wired up and unused" - it is simply not present.
- `floor_evaluation.py`'s loader returns one flat daily return series with no scenario, regime, or episode
  tagging attached; nothing downstream of it partitions the series at all.

**What is missing, precisely, to make this computable:**

1. An episode-level drawdown detector on the responder (trend) stream - something that identifies each
   drawdown's start, trough, end, and duration (this is the piece with no analogue anywhere in the repo
   today).
2. A rule assigning each identified episode to "fast" (① §4.2's Target-covered segment) or "protracted"
   (the segment §3.5(a) assigns to the responder), presumably on a duration threshold, which is not stated
   anywhere in the corpus either.
3. A conditioning mechanism parallel to `downside_correlation`'s quantile mask, but keyed to episode
   membership rather than daily-return magnitude - and the equivalent for `composite_allocator_utility`,
   since §3.5(c)(2) faults ΔΘ̂ specifically for returning "one number for the book" that "cannot say which
   segment the loss landed in."
4. Separate reporting of the fast-segment loss as a cost line against the Target's budget (§3.5(b)), which
   needs both the episode classifier above and a stated horizon/magnitude convention for what counts as
   the fast-segment loss.

None of the four exists. The docket's own remedy option - state the reported figure as unconditioned,
full-sample, and readable only as an Indeterminate result pending the segment-conditioned re-run - is
therefore the one the codebase currently supports; the segment-conditioned alternative is not available
to run today, not merely unrun.

## RM-7 - is the role-redundant verdict computable

**Verdict: the discriminating statistic does not exist anywhere in the codebase.**

The problem, restated in code terms: `composite_allocator_utility` already computes
`delta_theta = Θ̂(blend of responder+convergent) - Θ̂(responder alone at its current mandate weight)`
(see the RM-4 baseline trace above - the second term is exactly "responder at its own weight"). So
"seat earned"'s further test, "above the responder-only benchmark," cannot be this same subtraction
without collapsing into the row above it. The only comparison that stays distinct is an opportunity-cost
one: Θ̂(responder scaled up to consume the risk budget the convergent candidate would otherwise occupy)
minus Θ̂(responder at its current mandate weight) - i.e. a second, differently-scaled baseline, not the
one `delta_theta` already nets out.

Read the complete public API of `convergent.py` (`__all__`, lines 800-825): `block_length_band`,
`composite_allocator_utility`, `composite_book_utility`, `convergent_utility_rho_sensitivity_from_curve`,
`downside_correlation`, `evaluate_allocator_contribution`, `optimal_block_length`, plus the dataclasses
`AllocatorContribution` and `DeltaThetaInterval`. Every function that touches the responder leg
(`_blended_book`, `composite_book_utility`, `composite_allocator_utility`) takes a `convergent_weight`
that scales the *convergent* leg; none of them re-weights or re-levers the *responder* leg to a different
target. `evaluate_allocator_contribution`'s return type, `AllocatorContribution`, carries exactly two
point statistics (`delta_theta`, `downside_correlation`) plus resampling intervals on `delta_theta`
alone - there is no field, method, or sibling function anywhere that represents a scaled-responder
comparison.

Grepped `convergent.py` and `floor_evaluation.py` for `opportunity`, `scaled_responder`,
`responder_only`, `scale_up`, `leveraged`, "fixed risk budget": zero hits in either file. Read the whole
of `floor_evaluation.py` (168 lines) directly - it is the loader only, with no statistics of any kind, so
it could not carry this either.

This matches, and is independently confirmed by, `_review_r2.md`'s own concern 5 (lines 144-162), which
names the identical missing statistic in the identical terms ("Θ(responder scaled up to consume the risk
budget the convergent candidate would have used) minus Θ(responder at its current mandate weight)") and
states plainly it is "not currently named as implemented anywhere in `_sources.md`, `_buildability.md`,
or D8's own reported measurement." That review reasoned from what the corpus's own documentation claims
to implement; this pass reasoned from reading the module's actual source and confirms the same
conclusion by a different route.

**What would need to be built, and it does not exist today:** a function paralleling `_blended_book` that
constructs a "scaled-responder-only" book - the responder leg alone, re-weighted or re-levered to occupy
the same risk budget (`convergent_weight` × book vol, in whatever units the book actually allocates by)
the convergent candidate currently claims - and a matching `Θ̂` evaluation and, for consistency with the
rest of the module's discipline, a paired-resample interval around the resulting comparison. None of the
four pieces (the scaled-book constructor, its utility evaluation, the comparison itself, and inference
around it) is present.

Per the docket's own stated remedy, this is a research obligation to name as owed, on the same footing as
the fast-segment loss already flagged in RM-4/§3.5(b) - not a fix that can be made by relabeling or
recombining what already exists, since nothing that exists computes this comparison in any form.

## What the paper may now state

**On RM-9.** The paper may quote **+0.2724** as the downside-correlation guard, with its full
provenance: both live locked poles (`atalanta/trend_floor.yaml`, `demeter/carry_floor.yaml`), 1,889
common trading days (2019-01-02 to 2026-06-30), `downside_correlation(convergent_daily, trend_daily)`
at the default 10th-percentile conditioning on trend's worst days, `convergent_weight=0.4`, `rho=3.0`,
`book_vol_annual=0.10`. The paper must **not** quote +0.253 in any form, and should not describe the two
figures as measuring the same guard at different horizons - that explanation is foreclosed by
`downside_correlation` having no horizon parameter to vary. If the paper needs a sentence on the
discrepancy at all (§8, alongside the Tasche and smoothing caveats), the honest one is: a second, related
figure has circulated in commit messages and working notes without a reproducible computation behind it,
it is not used here, and it should be either derived from committed code or retracted before it appears
in any other document, including working run diaries that currently treat it as a live benchmark.

**On RM-4.** The paper may state, as a fact about the metric's own construction rather than an inference,
that the baseline in the reported ΔΘ̂ is the trend sleeve alone at the book's mandate volatility, and that
neither the Target nor the Expansion tier appears in either term of the subtraction. The paper should
state plainly that a segment-conditioned reading - splitting the guard and the contribution by fast versus
protracted drawdown episodes, per ① §4.2's own division of labour - is not buildable from what exists in
the codebase today, not merely unrun, and name the specific missing piece: an episode-level drawdown
classifier with a duration threshold, which has no precedent anywhere in this codebase. This licenses the
docket's remedy option directly: report the figure as unconditioned, full-sample, and Indeterminate,
pending that classifier being built.

**On RM-7.** The paper may state that the table's four-way discrimination between "role redundant" and
"seat earned" is aspirational rather than implemented, and name the specific statistic still owed: a
comparison of the blended book against the responder alone re-scaled to consume the convergent
candidate's risk budget, which is a different computation from anything `evaluate_allocator_contribution`
currently returns. This should be stated as a research obligation in the same register as the fast-segment
loss owed to the Target's budget (RM-4/§3.5(b)), not as a gap that could be closed by re-reading or
recombining the existing ΔΘ̂ and downside-correlation numbers.

## Limitations

**RM-9's +0.253 provenance is a negative result, not a traced one.** This pass establishes that no
committed code reproduces +0.253 or the accompanying lagged-correlation and autocorrelation figures in
the same commit message. It does not and cannot establish what computation actually produced those
numbers, since that computation (if it happened as an interactive session, which is the best available
explanation) left no artifact in the repository. If the original author has a notebook, shell history, or
memory of the exact call, that would settle it faster than anything available here.

**The staleness check was run but is time-bound.** `git log` and `git status` were checked at the start
and end of this pass; one commit (`0f26c5f3`, a Candidate-column indexing fix to the multi-candidate
sweep extractors) landed during this work and does not touch `downside_correlation`,
`composite_allocator_utility`, `_convergent_smoothing_index`, or the single-candidate locked-config
loader path any of the three figures in question depend on - confirmed by reading its diff. A working-tree
edit to `the-premium-is-rent-on-a-balance-sheet.md` (the D9 leverage-to-function correction) was already
reflected in the version read here. No guarantee holds for commits after this pass concludes.

**RM-4's episode-classifier gap is stated as absent, not as infeasible.** vectorbtpro, the simulation
library this codebase is built on, was not queried directly for drawdown-episode primitives (e.g. a
`Portfolio.drawdowns` accessor) - the finding is that nothing in this repository currently uses any such
primitive for this purpose, which is what "not computable today" means here. Whether the library exposes
one that could be wired in quickly, versus needing to be built from scratch, was not determined and would
change the size of the obligation named above, not its existence.

**RM-7's verdict rests on a complete read of one file's public surface plus a full read of its only
collaborator.** `convergent.py` (used in full) and `floor_evaluation.py` (read in full, 168 lines) are the
two files namable as candidates for this statistic given the loader-to-metric architecture the codebase
documents in its own docstrings. A grep across the broader `aegis_research` tree for the relevant terms
returned nothing, but a function computing this comparison under an unrelated name, in an unrelated
module, would not have been found by that method.

**Scope.** This pass did not re-verify anything the prior integrity passes (`_integrity.md`,
`_integrity_pass3.md`, `_integrity_rerun.md`) already checked outside these three items, and did not
re-run the test suite or execute any code - all findings are from static reading of source, commit
diffs, config files, and `bd`/`git` history.
